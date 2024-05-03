import os
import bids
import json
import importlib

from .. import schema

config_path = importlib.resources.path("forbids", "config")

configs = {}


def get_config(datatype):
    if datatype in ["anat", "func", "dwi", "swi" "fmap"]:
        modality = "mri"
    elif datatype in ["eeg", "meg"]:
        modality = "meeg"
    # TODO: add more datatype
    else:
        raise ValueError("unknown data type")
    if not modality in configs:
        with open(os.path.join(config_path, f"${modality}_tags.json")) as fd:
            configs[modality] = json.load(fd)
    return configs[modality]


def initialize(bids_layout: bids.BIDSLayout, session_uniform: bool = False) -> None:
    all_subjects = bids_layout.get_subjects()
    # get all jsons for a single subject
    all_sample_jsons = bids_layout.get(subject=all_subjects[0], extension=".json")

    # create union schema accross examplar subject for each BIDS entries
    for sample_json in all_sample_jsons:
        entities = sample_json.entities.copy()
        entities.pop("subject")
        all_subjects_jsons = bids_layout.get(**entities)
        config = get_config(entities["datatype"])

        all_metas = [sc.get_dict() for sc in all_subjects_jsons]

        sidecar_schema = schema.sidecars2unionschema(
            all_metas,
            bids_layout=bids_layout,
            discriminating_fields=config["instrument_tags"],
            config_props=config["properties"],
        )
        entities["subject"] = "ref"
        schema_path = bids_layout.build_path(entities, absolute_paths=False)
        schema_path_abs = os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER, schema_path)
        with open(schema_path_abs, "wt") as fd:
            fd.write(sidecar_schema.schema_json())
