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
    version_specific: bool = False,
    instrument_grouping_tags: tuple = tuple(),
) -> None:
    # generates schemas from examplar data for all unique set of entities
    # (but factoring subject, run and session if uniform_sessions)
    # attempts to group examplar data by shared instrument tags going from coarser to finer grouping
    # if uniform_instruments is false, it also allows to group per unique instruments

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
            generate_series_model(
                bids_layout,
                uniform_instruments=uniform_instruments,
                version_specific=version_specific,
                **series_entities,
            )


def generate_series_model(
    bids_layout: bids.BIDSLayout,
    uniform_instruments: bool = True,
    uniform_sessions: bool = True,
    version_specific: bool = False,
    **series_entities: dict,
):
    # generates schemas from examplar data for single set of entities describing the "series"
    # attempts to group examplar data by shared instrument tags going from coarser to finer grouping
    # if uniform_instruments is false, it also allows to group per unique instruments

    config = get_config(series_entities.get("datatype"))
    grouping_tags = config["instrument"]["grouping_tags"].copy()
    if not uniform_instruments:
        # add instrument-uid based grouping as the last resort
        grouping_tags.extend(config["instrument"]["uid_tags"])
    if version_specific:
        # add version-tag based grouping as the last resort
        grouping_tags.extend(config["instrument"]["version_tags"])

    # list all unique instruments and models for this datatype
    # unique_instruments = bids_layout.__getattr__(f"get_{config['instrument']['uid_tags'][0]}")(**series_entities)
    instrument_groups = OrderedDict(
        {tag: bids_layout.__getattr__(f"get_{tag}")(**series_entities) for tag in grouping_tags}
    )

    instrument_query_tags = []
    # try grouping from more global to finer, (eg. first manufacture, then scanner then scanner+coil, ...)
    for instrument_tag, _ in instrument_groups.items():
        # cumulate instrument tags for query
        instrument_query_tags.append(instrument_tag)
        # get all sidecars grouped by instrument tags

        non_null_entities = {k: v for k, v in series_entities.items() if v not in bids.layout.Query}
        series_sidecars = bids_layout.get(**series_entities)
        sidecars_by_instrument_group = {}
        # groups sidecars by instrument tags
        for sc in series_sidecars:
            instr_grp = tuple(
                (instr_tag, sc.get_dict().get(instr_tag, "unknown")) for instr_tag in instrument_query_tags
            )
            sidecars_by_instrument_group[instr_grp] = sidecars_by_instrument_group.get(instr_grp, []) + [sc]
        try:
            # attempt to generate the schema
            sidecar_schema = schema.sidecars2unionschema(
                sidecars_by_instrument_group,
                bids_layout=bids_layout,
                config_props=config["properties"],
                series_entities=non_null_entities,
                factor_entities=("subject", "run") + ("session",) if uniform_sessions else tuple(),
            )
        except ValidationError as e:
            logging.warning(f"failed to group with {instrument_query_tags}")
            logging.warning(e)
            continue
        # one grouping scheme worked !
        series_entities["subject"] = "ref"

        # generate paths and folder
        schema_path = bids_layout.build_path(non_null_entities, absolute_paths=False)
        schema_path_abs = os.path.join(bids_layout.root, schema.FORBIDS_SCHEMA_FOLDER, schema_path)
        os.makedirs(os.path.dirname(schema_path_abs), exist_ok=True)

        # serialize dataclass to json-schema, TODO: better handle serialization errors
        json_schema = deserialization_schema(sidecar_schema, additional_properties=True)
        # add BIDS custom json structure
        # TODO: set run number reqs semi-automatically, add tags based on examplar data
        json_schema["bids"] = {
            "instrument_tags": instrument_query_tags,
            "optional": False,
            "min_runs": 1,
            "max_runs": 1,
        }
        with open(schema_path_abs, "wt") as fd:
            json.dump(json_schema, fd, indent=2)

        logging.info("Successfully generated schema")
        break
