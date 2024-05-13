from __future__ import annotations

import itertools
import json
import logging
import os
from collections import OrderedDict
from importlib.resources import files

import bids
from apischema.json_schema import deserialization_schema
from jsonschema.exceptions import ValidationError

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
            with open(cfg_pth) as cfg_fd:
                configs[modality] = json.load(cfg_fd)
    return configs[modality]


def initialize(
    bids_layout: bids.BIDSLayout,
    uniform_instruments: bool = True,
    uniform_sessions: bool = False,
    instrument_grouping_tags: list = [],
) -> None:

    all_datatypes = bids_layout.get_datatype()

    excl_ents = ["subject", "run"] + (["session"] if uniform_sessions else [])

    for datatype in all_datatypes:
        logging.info(f"processing {datatype}")
        # list all unique sets of entities for this datatype
        # should results in 1+ set per series, unless scanner differences requires separate series
        # or results in different number of output series from the same sequence (eg. rec- acq-)
        unique_series_entities = []
        all_sidecars = bids_layout.get(datatype=datatype, extension=".json")
        for sidecar in all_sidecars:
            ents = tuple((k, v) for k, v in sidecar.entities.items() if k not in excl_ents)
            if ents not in unique_series_entities:
                unique_series_entities.append(ents)

        for series_entities in unique_series_entities:
            series_entities = dict(series_entities)
            for entity in schema.ALT_ENTITIES:
                if entity not in series_entities:
                    series_entities[entity] = bids.layout.Query.NONE
            logging.info(series_entities)
            generate_series_model(bids_layout, uniform_instruments=uniform_instruments, **series_entities)


def generate_series_model(
    bids_layout: bids.BIDSLayout,
    uniform_instruments: bool = True,
    uniform_sessions: bool = True,
    **series_entities: dict,
):

    config = get_config(series_entities.get("datatype"))

    # list all unique instruments and models for this datatype
    # unique_instruments = bids_layout.__getattr__(f"get_{config['instrument']['uid_tags'][0]}")(**series_entities)
    instrument_groups = OrderedDict(
        {tag: bids_layout.__getattr__(f"get_{tag}")(**series_entities) for tag in config["instrument"]["grouping_tags"]}
    )

    instrument_query_tags = []
    # try grouping from more global to finer, (eg. first manufacture, then scanner then scanner+coil, ...)
    for instrument_tag, _ in instrument_groups.items():
        # cumulate instrument tags for query
        instrument_query_tags.append(instrument_tag)
        # get all sidecars grouped by instrument tags

        non_null_entities = {k: v for k, v in series_entities.items() if v not in bids.layout.Query}
        series_sidecars = bids_layout.get(**series_entities)
        sidecars_by_instrument_group = itertools.groupby(
            series_sidecars,
            lambda x: tuple(x.get_dict().get(instr_tag, "unknown") for instr_tag in instrument_query_tags),
        )
        try:
            sidecar_schema = schema.sidecars2unionschema(
                sidecars_by_instrument_group,
                bids_layout=bids_layout,
                config_props=config["properties"],
                series_entities=non_null_entities,
                factor_entities=("subject", "run") + ("session",) if uniform_sessions else tuple(),
            )
        except ValidationError as e:
            logging.warn(f"failed to group with {instrument_query_tags}")
            logging.warn(e)
            continue
        series_entities["subject"] = "ref"
        schema_path = bids_layout.build_path(non_null_entities, absolute_paths=False)
        schema_path_abs = os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER, schema_path)
        os.makedirs(os.path.dirname(schema_path_abs), exist_ok=True)

        json_schema = deserialization_schema(sidecar_schema, additional_properties=True)
        with open(schema_path_abs, "wt") as fd:
            json.dump(json_schema, fd, indent=2)

        logging.info("Successfully generated schema")
        break


def trash():
    all_subjects = bids_layout.get_subjects()
    # get all jsons for a single subject
    all_sample_jsons = bids_layout.get(subject=all_subjects[0], extension=".json")

    # create union schema across examplar subject for each BIDS entries
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

        sidecar_schema = schema.sidecars2unionschema(
            all_subjects_jsons,
            bids_layout=bids_layout,
            discriminating_fields=config["instrument_tags"],
            config_props=config["properties"],
            factor_entities=("subject", "run") + ("session",) if uniform_sessions else tuple(),
        )

        entities["subject"] = "ref"
        if uniform_sessions:
            entities.pop("session", None)
        schema_path = bids_layout.build_path(entities, absolute_paths=False)
        schema_path_abs = os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER, schema_path)
        os.makedirs(os.path.dirname(schema_path_abs), exist_ok=True)

        json_schema = deserialization_schema(sidecar_schema, additional_properties=True)
        with open(schema_path_abs, "wt") as fd:
            json.dump(json_schema, fd, indent=2)
    logging.info("Successfully generated schema")
