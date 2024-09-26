from __future__ import annotations

import keyword
import logging
import os
from typing import  Any, List, Optional, Iterator

import bids
import jsonschema.validators
from jsonschema.exceptions import ValidationError
from jsonschema._typing import Validator

from .. import schema

lgr = logging.getLogger(__name__)

class BIDSFileError(ValidationError):
    # class to represent error of BIDS file missing or unexpected
    pass
"""
    def __init__(self, message, path=None, missing=True):
        self.path = path
        self.missing = missing

"""



def validate(bids_layout: bids.BIDSLayout, **entities: dict[str, str|list]):
    # validates the data specified by entities using the schema present in the `.forbids` folder

    ref_layout = bids.BIDSLayout(os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER), validate=False)

    # get sidecars for the session or ones factored at a higher level
    ref_sidecars = ref_layout.get(session=[entities.get("session"), None], extension=".json")

    all_sidecars = bids_layout.get(extension=".json", **entities)
    print(entities, len(all_sidecars))

    subjects = bids_layout.get_subject(subject = entities.pop('subject'))

    is_multisession = len(bids_layout.get_session())
    is_session_specific = len(ref_layout.get_session())
    if is_multisession:
        lgr.info("The dataset is multi-session.")

    all_sidecars = bids_layout.get(
        extension=".json",
        subject=subjects,
        session=entities['session'],
    )


    for ref_sidecar in ref_sidecars:
        lgr.info(f"validating {ref_sidecar.relpath}")
        # load the schema
        sidecar_schema = ref_sidecar.get_dict()
        bidsfile_constraints = sidecar_schema.pop("bids", dict())
        query_entities = ref_sidecar.entities.copy()

        validator = schema.get_validator(sidecar_schema)

        for subject in subjects:
            query_entities["subject"] = subject
            sessions = bids_layout.get_session(
                subject = subject,
                session = entities["session"]
            )

            for session in sessions:
                query_entities["session"] = session

                lgr.debug(query_entities)

                sidecars_to_validate = bids_layout.get(**query_entities)

                if not sidecars_to_validate and not bidsfile_constraints.get("optional", False):
                    yield BIDSFileError(f"{ref_sidecar.relpath} found no match")
                    continue # no point going further

                num_sidecars = len(sidecars_to_validate)
                min_runs = bidsfile_constraints.get("min_runs", 0)
                max_runs = bidsfile_constraints.get("max_runs", 1e10)
                if num_sidecars < min_runs:
                    yield BIDSFileError(f"Expected at least {min_runs} runs for {ref_sidecar.relpath}, found {num_sidecars}")
                elif num_sidecars > max_runs:
                    yield BIDSFileError(f"Expected at most {max_runs} runs for {ref_sidecar.relpath}, found {num_sidecars}")

                for sidecar in sidecars_to_validate:
                    if sidecar in all_sidecars:
                        all_sidecars.remove(sidecar)
                    else:
                        lgr.error("an error occurred")
                    lgr.info(f"validating {sidecar.path}")
                    sidecar_data = schema.prepare_metadata(sidecar, bidsfile_constraints["instrument_tags"])
                    yield from validator.iter_errors(sidecar_data)
    for extra_sidecar in all_sidecars:
        relpath = extra_sidecar.path
        yield BIDSFileError(f"Unexpected BIDS file{extra_sidecar.relpath}")
