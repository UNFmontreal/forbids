import os
import bids
import jsonschema.validators


from .. import schema


class ValidationError(ValueError):
    pass


class BIDSFileError(ValidationError):
    pass


def validate(bids_layout: bids.BIDSLayout, **entities):
    from .. import schema

    ref_layout = bids.BIDSLayout(os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER), validate=False)

    # get sidecars for the session or ones factored at a higher level
    ref_sidecars = ref_layout.get(session=[entities.get("session"), None], extension=".json")

    for ref_sidecar in ref_sidecars:
        # load the schema
        schema = ref_sidecar.get_dict()
        bidsfile_constraints = schema.pop("bids", dict())
        lookup_ents = ref_sidecar.entities.copy()
        lookup_ents["subject"] = entities.get("subject")
        lookup_ents["session"] = entities.get("session", None)

        sidecars_to_validate = bids_layout.get(**lookup_ents)
        if not sidecars_to_validate and not bidsfile_constraints.get("optional", False):
            yield BIDSFileError(ref_sidecar)
        num_sidecars = len(sidecars_to_validate)
        min_runs = bidsfile_constraints.get("min_runs", 0)
        max_runs = bidsfile_constraints.get("max_runs", 1e10)
        if num_sidecars < min_runs:
            yield BIDSFileError("Expected at least {min_runs} runs for {ref_sidecar}, found {num_sidecars}")
        elif num_sidecars > max_runs:
            yield BIDSFileError("Expected at most {max_runs} runs for {ref_sidecar}, found {num_sidecars}")

        validator_cls = jsonschema.validators.validator_for(schema)
        validator = validator_cls(schema)

        for sidecar in sidecars_to_validate:
            yield from validator.iter_errors(sidecar.get_dict())
