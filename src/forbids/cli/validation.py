import os
import bids
import logging
import keyword
import jsonschema.validators


from .. import schema


class ValidationError(ValueError):
    pass


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
            yield BIDSFileError(ref_sidecar)
        num_sidecars = len(sidecars_to_validate)
        min_runs = bidsfile_constraints.get("min_runs", 0)
        max_runs = bidsfile_constraints.get("max_runs", 1e10)
        if num_sidecars < min_runs:
            yield BIDSFileError("Expected at least {min_runs} runs for {ref_sidecar}, found {num_sidecars}")
        elif num_sidecars > max_runs:
            yield BIDSFileError("Expected at most {max_runs} runs for {ref_sidecar}, found {num_sidecars}")

        validator_cls = jsonschema.validators.validator_for(sidecar_schema)
        validator = validator_cls(sidecar_schema)

        for sidecar in sidecars_to_validate:
            all_sidecars.remove(sidecar)
            logging.info(f"validating {sidecar.path}")
            sidecar_content = {k + ("__" if k in keyword.kwlist else ""): v for k, v in sidecar.get_dict().items()}
            yield from validator.iter_errors(sidecar_content)
    for extra_sidecar in all_sidecars:
        yield BIDSExtraError(f"Extra BIDS file{extra_sidecar.path}")
