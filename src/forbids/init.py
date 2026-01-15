"""Initialization module for forBIDS schema generation.

This module handles the initialization of forBIDS schemas from exemplar BIDS datasets.
It analyzes existing BIDS data to generate JSON schemas that can be used for protocol
compliance validation. The module supports multi-site and multi-vendor studies by
grouping data based on instrument characteristics.
"""
#   -------------------------------------------------------------
#   Licensed under the MIT License. See LICENSE in project root for information.
#   -------------------------------------------------------------
from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from importlib.resources import files

import bids
from apischema.json_schema import deserialization_schema
from jsonschema.exceptions import ValidationError

from . import schema

configs = {}
lgr = logging.getLogger(__name__)
DEBUG = bool(os.environ.get("DEBUG", False))
lgr.setLevel(logging.DEBUG if DEBUG else logging.INFO)


def get_config(datatype):
    """Load configuration for a specific BIDS datatype.

    Loads and caches the configuration file containing validation presets
    for metadata tags specific to the given datatype. Configurations are
    cached after first load for efficiency.

    Args:
        datatype: BIDS datatype (e.g., "anat", "func", "dwi", "fmap", "eeg", "meg").

    Returns:
        Dictionary containing:
            - "instrument": Instrument tag configuration (grouping, uid, version tags)
            - "properties": Metadata validation presets for each property

    Raises:
        ValueError: If datatype is not recognized.

    Examples:
        >>> config = get_config("anat")
        >>> "Manufacturer" in config["properties"]
        True
    """
    # Map BIDS datatypes to instrument types
    if datatype in ["anat", "func", "dwi", "swi", "fmap"]:
        instrument = "mri"
    elif datatype == "eeg":
        instrument = "eeg"
    elif datatype == "meg":
        instrument = "meg"
    elif datatype == "pet":
        instrument = "pet"
    elif datatype == "ieeg":
        instrument = "ieeg"
    # TODO: add more datatypes (nirs, motion, etc.)
    else:
        raise ValueError(f"unknown data type: {datatype}")

    if instrument not in configs:
        with files("forbids").joinpath(f"config/{instrument}_tags.json") as cfg_pth:
            lgr.debug("loading config %s", cfg_pth)
            with open(cfg_pth) as cfg_fd:
                configs[instrument] = json.load(cfg_fd)
        configs[instrument]["properties"]["__instrument__"] = "="
    return configs[instrument]


def initialize(
    bids_layout: bids.BIDSLayout,
    uniform_instruments: bool = True,
    uniform_sessions: bool = False,
    version_specific: bool = False,
    instrument_grouping_tags: tuple = tuple(),
) -> None:
    """Initialize forBIDS schemas from a BIDS dataset.

    Generates JSON schemas for all unique series in the dataset by analyzing
    exemplar data. Schemas are saved to the `.forbids` folder within the BIDS
    dataset root.

    The function groups data by instrument characteristics (manufacturer, model, etc.)
    and creates schemas that can validate protocol compliance across subjects and sessions.

    Args:
        bids_layout: PyBIDS BIDSLayout object for the dataset.
        uniform_instruments: If True, create schemas that work across all instruments
            of the same manufacturer/model. If False, allow instrument-specific schemas.
        uniform_sessions: If True, create schemas that work across all sessions.
            If False, allow session-specific schemas for longitudinal studies.
        version_specific: If True, allow schemas to be specific to scanner software version.
        instrument_grouping_tags: Additional custom tags for instrument grouping.

    Returns:
        True if all schemas were successfully generated, False otherwise.

    Examples:
        >>> layout = bids.BIDSLayout("/data/my_bids_dataset")
        >>> success = initialize(layout, uniform_instruments=True)
        >>> # Schemas are now in /data/my_bids_dataset/.forbids/
    """
    # generates schemas from examplar data for all unique set of entities
    # (but factoring subject, run and session if uniform_sessions)
    # attempts to group examplar data by shared instrument tags going from coarser to finer grouping
    # if uniform_instruments is false, it also allows to group per unique instruments

    all_datatypes = bids_layout.get_datatype()

    # group by instrument tags across subject, (session) and runs
    excl_ents = ["subject", "run"] + (["session"] if uniform_sessions else [])

    successes = []

    for datatype in all_datatypes:
        lgr.info("processing %s", datatype)
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
            success = generate_series_model(
                bids_layout,
                uniform_instruments=uniform_instruments,
                version_specific=version_specific,
                **series_entities,
            )
            successes.append(success)
    return all(successes)


def generate_series_model(
    bids_layout: bids.BIDSLayout,
    uniform_instruments: bool = True,
    uniform_sessions: bool = True,
    version_specific: bool = False,
    **series_entities: dict,
):
    """Generate a schema model for a specific BIDS series.

    Creates a JSON schema for a single series (identified by BIDS entities like
    datatype, suffix, etc.) by analyzing exemplar data and grouping by instrument
    characteristics. The function tries different grouping strategies from coarse
    to fine-grained until finding one that works.

    Args:
        bids_layout: PyBIDS BIDSLayout object for the dataset.
        uniform_instruments: If True, group across all instruments of same type.
        uniform_sessions: If True, group across all sessions.
        version_specific: If True, include software version in grouping.
        **series_entities: BIDS entities identifying the series (e.g., datatype="anat", suffix="T1w").

    Returns:
        True if schema was successfully generated and saved, False otherwise.

    Notes:
        The function attempts grouping strategies in order:
        1. By manufacturer
        2. By manufacturer + model
        3. By manufacturer + model + coil
        4. (If uniform_instruments=False) By device serial number
        5. (If version_specific=True) By software version

        The first grouping that successfully validates all exemplars is used.
    """
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
        {tag: getattr(bids_layout, f"get_{tag}")(**series_entities) for tag in grouping_tags}
    )

    instrument_query_tags = []
    # try grouping from more global to finer, (eg. first manufacturer, then scanner, then scanner+coil, ...)
    for instrument_tag, _ in instrument_groups.items():
        # cumulate instrument tags for query
        instrument_query_tags.append(instrument_tag)

        non_null_entities = {k: v for k, v in series_entities.items() if not isinstance(v, bids.layout.Query)}
        series_sidecars = bids_layout.get(**series_entities)
        series_subjects = bids_layout.get_subjects(**series_entities)
        sidecars_by_instrument_group = {}
        # groups sidecars by instrument tags
        for sc in series_sidecars:
            sidecar_data = sc.get_dict()
            instr_grp = tuple(
                (instr_tag, sidecar_data.get(instr_tag, "unknown")) for instr_tag in instrument_query_tags
            )
            sidecars_by_instrument_group[instr_grp] = sidecars_by_instrument_group.get(instr_grp, []) + [sc]

        instrument_grouped_subjects = bids_layout.get_subjects(**dict(instr_grp))
        # if that grouping gets more subject we need to be more specific
        if set(series_subjects) != set(instrument_grouped_subjects):
            continue

        try:
            # attempt to generate the schema
            sidecar_schema = schema.sidecars2unionschema(
                sidecars_by_instrument_group,
                bids_layout=bids_layout,
                config_props=config["properties"],
                series_entities=non_null_entities,
                factor_entities=("subject", "run") + ("session",) if uniform_sessions else tuple(),
            )
        except ValidationError as error:
            lgr.warning("failed to group with %s", str(instrument_query_tags))
            lgr.warning(
                "%s %s : %s found %s",
                error.__class__.__name__,
                ".".join([str(e) for e in error.absolute_path]),
                error.message,
                error.instance if "required" not in error.message else "",
            )
            continue  # move on to next instrument grouping

        instruments_non_optional = set()
        # one instrument grouping scheme worked!
        runs_per_session = []
        for subject in bids_layout.get_subjects():
            for session in bids_layout.get_session(subject=subject) or [bids.layout.Query.NONE]:
                session_series = bids_layout.get(subject=subject, session=session, **series_entities)
                num_series = len(session_series)
                runs_per_session.append(num_series)
                if num_series:
                    instruments_non_optional.add(
                        schema.get_instrument_key(session_series[0].get_dict(), instrument_query_tags)
                    )
        # generate paths and folder
        non_null_entities["subject"] = "ref"
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
            "required_for_instruments": list(instruments_non_optional),
            "min_runs": min(runs_per_session),
            "max_runs": max(runs_per_session),
        }
        with open(schema_path_abs, "wt") as fd:
            json.dump(json_schema, fd, indent=2)

        lgr.info("Successfully generated schema with grouping %s", str(instrument_query_tags))
        return True
    else:
        lgr.error("failed to generate a schema for %s", str(series_entities))
        return False
