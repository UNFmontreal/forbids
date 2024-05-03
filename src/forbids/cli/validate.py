import os
import bids
import pydantic
from .. import schema
from jsonschema import validate


def validate(bids_layout: bids.BIDSLayout, **entities):

    ref_layout = bids.BIDSLayout(os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER))

    sidecars_to_check = bids_layout.get(**entities, extension=".json")

    for sidecar in sidecars_to_check:
        entities = sidecar.entities.copy()
        entities["subject"] = "ref"
        schema_file = ref_layout.get(**entities)
        if not schema_file:
            entities.pop("session")
            schema_file = ref_layout.get(**entities)
        schema = schema_file.get_dict())

        schema.validate