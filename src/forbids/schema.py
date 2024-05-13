from __future__ import annotations

import keyword
import logging
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, make_dataclass
from typing import Annotated, Any, Iterator, Literal, NewType, Tuple, Union

import bids.layout
from apischema import discriminator, schema

FORBIDS_SCHEMA_FOLDER = ".forbids"


# entities that differentiate files from the same series
# where it might be None for one of the files.
ALT_ENTITIES = ["reconstruction", "acquisition"]


def tagpreset2type(tag: str, tag_preset: str, value: Any):
    # Converts tag presets from config files into a typing with constraints

    # Parameters:
    #   tag: the name of the tag
    #   tag_preset: the expression to set constraint from
    #   value: the examplar value to determine type and set constants

    # Returns:
    #   type: a python type with added apischema constraints
    if tag_preset == "=":
        if isinstance(value, list):
            return Tuple[*[Literal[vv] for vv in value]]
        else:
            return Literal[value]
    elif tag_preset == "*":
        return type(value)
    elif tag_preset.startswith("~="):
        tag = NewType(tag, type(value))
        tol = float(tag_preset[2:])
        schema(min=value - tol, max=value + tol)(tag)
        return tag
    elif tag_preset.startswith("r"):
        tag = NewType(tag, type(value))  # likely a string, check if this need enforcement
        schema(pattern=re.compile(tag_preset[1:]))(tag)
        return tag
    else:
        raise RuntimeError(f"Unsupported constraint for {tag} in the config file.")


def dict2schemaprops(sidecar: dict, config_props: dict, schema_path: str) -> Iterator:
    # from a example dictionary and matching config, generate dataclass fields definitions
    # recursively creates subschema for dictionary values

    # Parameters:
    # sidecar: dict with examplar values to determine type and constant
    # config_props: dict with preset of how to validate tags
    # schema_path: schema name to be postpended in recursive schema defs for uniqness
    for k, tag_preset in config_props.items():
        if k in sidecar:
            v = sidecar[k]
            k2 = k + ("__" if k in keyword.kwlist else "")
            if isinstance(config_props[k], dict):
                yield k2, sidecar2schema(v, tag_preset, f"{schema_path}_{k}")
            else:
                yield k2, tagpreset2type(f"{schema_path}_{k}", tag_preset, v)


def sidecar2schema(sidecar: dict, config_props: dict, subschema_name: str):
    # from a examplar sidecar and config, generate a schema

    # Parameters:
    # sidecar: examplar sidecar
    # config_props: schema properties config
    # subschema_name: name to give the subschema
    return make_dataclass(subschema_name, fields=list(dict2schemaprops(sidecar, config_props, subschema_name)))


def sidecars2unionschema(
    sidecars: list[bids.layout.BIDSJSONFile],
    bids_layout: bids.BIDSLayout,
    discriminating_fields: list[str],
    config_props: dict,
    factor_entities: tuple = ("subject", "run"),
) -> Annotated:
    # from a set of sidecars from different scanners generate a meta-schema

    #
    series_entities = [{k: v for k, v in sc.entities.items() if k not in factor_entities} for sc in sidecars]
    # TODO: not assume we have exact entities set for all sidecars
    # skip validation for now, doesn't work with UNIT1
    schema_name = bids_layout.build_path(series_entities[0], absolute_paths=False, validate=False)
    subschemas = {}
    subschemas_metas = {}
    for sc in sidecars:
        logging.info(f"generating schema from {sc.path}")
        metas = sc.get_dict()
        sc_main_discriminating_value = metas.get(discriminating_fields[0], None)
        if not sc_main_discriminating_value:
            raise RuntimeError(f"sidecar {sc} do no contains discrinating value {discriminating_fields[0]}")
        sc_discriminating_values = [metas[df].replace(".", "_") for df in discriminating_fields if df in metas]
        subschema_name = schema_name + "-".join(sc_discriminating_values)
        # while subschema_name in subschemas:
        #    subschema_name = subschema_name + "_copy"
        subschema = sidecar2schema(metas, config_props, subschema_name)
        if sc_main_discriminating_value in subschemas:
            logging.debug(
                f"{discriminating_fields[0]}: {sc_main_discriminating_value} -------- {sc_discriminating_values}"
            )
            match_discriminating_values = [
                subschemas_metas[sc_main_discriminating_value][df].replace(".", "_")
                for df in discriminating_fields
                if df in metas
            ]
            logging.debug(str(match_discriminating_values))
            if compare_schema(subschema, subschemas[sc_main_discriminating_value]):
                continue
            else:
                print(f"cannot reconcile 2 schemas with same discriminating value")
        else:
            subschemas[sc_main_discriminating_value] = subschema
            subschemas_metas[sc_main_discriminating_value] = metas

    if len(subschemas) == 1:
        return subschemas[subschema_name]

    UnionModel = Annotated[Union[tuple(subschemas.values())], discriminator(discriminating_fields[0], subschemas)]

    return UnionModel


def compare_schema(sc1: dataclass, sc2: dataclass) -> bool:
    match = True

    sc1_props = sc1.__dataclass_fields__
    sc2_props = sc2.__dataclass_fields__
    sc1_props_keys = set(sc1_props.keys())
    sc2_props_keys = set(sc2_props.keys())
    logging.debug(f"XOR: {set(sc1_props_keys).symmetric_difference(sc2_props_keys)}")
    for prop in sc1_props_keys.intersection(sc2_props_keys):
        if isinstance(sc1_props[prop], type):
            match = compare_schema(sc1_props[prop], sc2_props[prop])
        t1, t2 = sc1_props[prop].type, sc2_props[prop].type
        if t1 != t2:
            if not hasattr(t1, "__supertype__") or t1.__supertype__ != t2.__supertype__:
                logging.debug(str((prop, sc1_props[prop].type, sc2_props[prop].type)))
                match = False
    return match
