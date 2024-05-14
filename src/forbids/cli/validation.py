from __future__ import annotations

import keyword
import logging
import os

import bids
import jsonschema.validators
from jsonschema.exceptions import ValidationError

from .. import schema


class BIDSFileError(ValidationError):
    pass


class BIDSExtraError(ValidationError):
    pass


def validate(bids_layout: bids.BIDSLayout, **entities):

    ref_layout = bids.BIDSLayout(os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER), validate=False)

    # get sidecars for the session or ones factored at a higher level
    ref_sidecars = ref_layout.get(session=[entities.get("session"), None], extension=".json")

    all_sidecars = bids_layout.get(extension=".json", **entities)

    for ref_sidecar in ref_sidecars:
        # load the schema
        sidecar_schema = ref_sidecar.get_dict()
        bidsfile_constraints = sidecar_schema.pop("bids", dict())
        query_entities = ref_sidecar.entities.copy()
        query_entities["subject"] = entities.get("subject")
        query_entities["session"] = entities.get("session", None)

        for entity in schema.ALT_ENTITIES:
            if entity not in query_entities:
                query_entities[entity] = bids.layout.Query.NONE
        sidecars_to_validate = bids_layout.get(**query_entities)
        if not sidecars_to_validate and not bidsfile_constraints.get("optional", False):
            yield BIDSFileError(f"{ref_sidecar} found no match")
        num_sidecars = len(sidecars_to_validate)
        min_runs = bidsfile_constraints.get("min_runs", 0)
        max_runs = bidsfile_constraints.get("max_runs", 1e10)
        if num_sidecars < min_runs:
            yield BIDSFileError("Expected at least {min_runs} runs for {ref_sidecar}, found {num_sidecars}")
        elif num_sidecars > max_runs:
            yield BIDSFileError("Expected at most {max_runs} runs for {ref_sidecar}, found {num_sidecars}")

        validator = schema.get_validator(sidecar_schema)

        for sidecar in sidecars_to_validate:
            if sidecar in all_sidecars:
                all_sidecars.remove(sidecar)
            else:
                logging.error("an error occurred")
            logging.info(f"validating {sidecar.path}")
            sidecar_data = schema.prepare_metadata(sidecar, bidsfile_constraints["instrument_tags"])
            yield from validator.iter_errors(sidecar_data)
    for extra_sidecar in all_sidecars:
        yield BIDSExtraError(f"Extra BIDS file{extra_sidecar.path}")
