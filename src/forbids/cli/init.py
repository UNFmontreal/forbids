import os
import bids
import json
import logging
from apischema.json_schema import deserialization_schema
from importlib.resources import files

from .. import schema

configs = {}


def get_config(datatype):
    if datatype in ["anat", "func", "dwi", "swi", "fmap"]:
        modality = "mri"
    elif datatype in ["eeg", "meg"]:
        modality = "meeg"
    # TODO: add more datatype
    else:
        raise ValueError("unknown data type")
    if modality not in configs:
        with files("forbids").joinpath(f"config/{modality}_tags.json") as cfg_pth:
            logging.debug(f"loading config {cfg_pth}")
            with open(cfg_pth, "r") as cfg_fd:
                configs[modality] = json.load(cfg_fd)
    return configs[modality]


def initialize(bids_layout: bids.BIDSLayout, session_uniform: bool = False) -> None:
    all_subjects = bids_layout.get_subjects()
    # get all jsons for a single subject
    all_sample_jsons = bids_layout.get(subject=all_subjects[0], extension=".json")

    # create union schema accross examplar subject for each BIDS entries
    for sample_json in all_sample_jsons:
        entities = sample_json.entities.copy()
        if entities["suffix"] in ["scans"]:
            continue
        query_entities = entities.copy()
        for entity in schema.ALT_ENTITIES:
            if entity not in query_entities:
                query_entities[entity] = bids.layout.Query.NONE
        query_entities.pop("subject")

        all_subjects_jsons = bids_layout.get(**query_entities)
        config = get_config(entities["datatype"])

        sidecar_schema = schema.sidecars2unionschema(
            all_subjects_jsons,
            bids_layout=bids_layout,
            discriminating_fields=config["instrument_tags"],
            config_props=config["properties"],
            factor_entities=("subject", "run") + ("session",) if session_uniform else tuple(),
        )

        entities["subject"] = "ref"
        if session_uniform:
            entities.pop("session")
        schema_path = bids_layout.build_path(entities, absolute_paths=False)
        schema_path_abs = os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER, schema_path)
        os.makedirs(os.path.dirname(schema_path_abs), exist_ok=True)

        json_schema = deserialization_schema(sidecar_schema, additional_properties=True)
        with open(schema_path_abs, "wt") as fd:
            json.dump(json_schema, fd)
    logging.info("Successfully generated schema")
