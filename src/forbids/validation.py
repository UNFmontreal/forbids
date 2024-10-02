from __future__ import annotations

import logging
import os

import bids
from jsonschema._utils import Unset
from jsonschema.exceptions import ValidationError

from . import schema

lgr = logging.getLogger(__name__)


class BIDSJSONError(ValidationError):
    # class to represent BIDS metadata error
    pass


class BIDSFileError(ValidationError):
    # class to represent error of BIDS file missing or unexpected
    pass


def validate(bids_layout: bids.BIDSLayout, **entities: dict[str, str | list]):
    # validates the data specified by entities using the schema present in the `.forbids` folder

    ref_layout = bids.BIDSLayout(os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER), validate=False)

    # get sidecars for the session or ones factored at a higher level
    ref_sidecars = ref_layout.get(session=[entities.get("session"), None], extension=".json")

    all_sidecars = bids_layout.get(extension=".json", **entities)

    subjects = bids_layout.get_subject(subject=entities.pop("subject"))

    is_multisession = len(bids_layout.get_session())
    is_session_specific = len(ref_layout.get_session())
    if is_multisession:
        lgr.info("The dataset is multi-session.")

    all_sidecars = bids_layout.get(
        extension=".json",
        subject=subjects,
        session=entities["session"],
    )

    for ref_sidecar in ref_sidecars:
        lgr.info("validating %s", str(ref_sidecar.relpath))
        # load the schema
        sidecar_schema = ref_sidecar.get_dict()
        bidsfile_constraints = sidecar_schema.pop("bids", dict())
        query_entities = ref_sidecar.entities.copy()

        for entity in schema.ALT_ENTITIES:
            if entity not in query_entities:
                query_entities[entity] = bids.layout.Query.NONE
        validator = schema.get_validator(sidecar_schema)

        for subject in subjects:
            query_entities["subject"] = subject
            if is_session_specific:
                sessions = [query_entities["session"]]
            else:
                sessions = bids_layout.get_session(subject=subject, session=entities["session"]) or [
                    bids.layout.Query.NONE
                ]

            for session in sessions:
                lgr.info("validating sub-%s %s", subject, "ses-" + session if isinstance(session, str) else "")
                query_entities["session"] = session
                non_null_entities = {k: v for k, v in query_entities.items() if not isinstance(v, bids.layout.Query)}
                expected_sidecar = bids_layout.build_path(non_null_entities, absolute_paths=False)

                lgr.debug(query_entities)

                sidecars_to_validate = bids_layout.get(**query_entities)

                if not sidecars_to_validate and not bidsfile_constraints.get("optional", False):
                    yield BIDSFileError(f"{expected_sidecar}", "no match")
                    continue  # no point going further

                num_sidecars = len(sidecars_to_validate)
                min_runs = bidsfile_constraints.get("min_runs", 0)
                max_runs = bidsfile_constraints.get("max_runs", 1e10)

                if num_sidecars < min_runs:
                    yield BIDSFileError(
                        f"Expected at least {min_runs} runs for {expected_sidecar}, found {num_sidecars}"
                    )
                elif num_sidecars > max_runs:
                    yield BIDSFileError(
                        f"Expected at most {max_runs} runs for {expected_sidecar}, found {num_sidecars}"
                    )

                for sidecar in sidecars_to_validate:
                    if sidecar in all_sidecars:
                        all_sidecars.remove(sidecar)
                    else:
                        lgr.error("an error occurred")
                    lgr.debug("validating %s", sidecar.relpath)
                    sidecar_data = schema.prepare_metadata(sidecar, bidsfile_constraints["instrument_tags"])
                    yield from add_path_note_to_error(validator, sidecar_data, sidecar.relpath)
    for extra_sidecar in all_sidecars:
        yield BIDSFileError("Unexpected BIDS file %s", extra_sidecar.relpath)


def add_path_note_to_error(validator, sidecar_data, filepath):
    # add the path to the json files that triggers the error
    # for better reporting in process_validation

    for error in validator.iter_errors(sidecar_data):
        error.add_note(filepath)
        yield error


def process_validation(layout, subject, session):
    # run validation on the BIDS layout and specified subject/session
    # format errors for not-to-verbose pretty printing

    no_error = True
    for error in validate(layout, subject=subject, session=session):
        no_error = False

        formatted_message = error.message
        if len(error.path) == 0 and not isinstance(error.instance, Unset):
            formatted_message = f"non-existing schema for instrument {error.instance['__instrument__']}"

        lgr.error(
            "%s %s %s : %s",
            error.__class__.__name__,
            error.__notes__[0] if hasattr(error, "__notes__") else "",
            ".".join([str(e) for e in error.absolute_path]),
            formatted_message,
        )
        lgr.debug(error)
    return no_error
