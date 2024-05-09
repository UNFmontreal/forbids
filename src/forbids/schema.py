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
ALT_ENTITIES = ["reconstruction"]


def tagpreset2type(tag: str, tag_preset: str, value: Any):
    if tag_preset == "=":
        if isinstance(value, list):
            return Tuple[*[Literal[vv] for vv in value]]
        else:
            return Literal[value]
    elif tag_preset == "*":
        print("here")
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


def dict2schemaprops(sidecar: dict, config_props: dict) -> Iterator:
    for k, v in sidecar.items():
        if k in config_props:
            k2 = k + ("__" if k in keyword.kwlist else "")
            if isinstance(config_props[k], dict):
                yield k2, sidecar2schema(v, config_props[k], k), field()
            else:
                yield k2, *tagpreset2type(k, config_props[k], v)


def sidecar2schema(sidecar: dict, config_props: dict, subschema_name: str):
    return make_dataclass(subschema_name, fields=list(dict2schemaprops(sidecar, config_props)))


def sidecars2unionschema(
    sidecars: list[bids.layout.BIDSJSONFile],
    bids_layout: bids.BIDSLayout,
    discriminating_fields: list[str],
    config_props: dict,
    factor_entities: tuple = ("subject", "run"),
) -> Annotated:

    series_entities = [{k: v for k, v in sc.entities.items() if k not in factor_entities} for sc in sidecars]
    # TODO: not assume we have exact entities set for all sidecars
    # skip validation for now, doesn't work with UNIT1
    schema_name = bids_layout.build_path(series_entities[0], absolute_paths=False, validate=False)
    subschemas = {}
    for sc in sidecars:
        logging.info(f"generating schema from {sc.path}")
        metas = sc.get_dict()
        sc_main_discriminating_value = metas.get(discriminating_fields[0], None)
        if not sc_main_discriminating_value:
            raise RuntimeError(f"sidecar {sc} do no contains discrinating value {discriminating_fields[0]}")
        sc_discriminating_values = [metas.get(df) for df in discriminating_fields if df in metas]
        subschema_name = schema_name + "-".join(sc_discriminating_values)
        while subschema_name in subschemas:
            subschema_name = subschema_name + "_copy"
        subschema = sidecar2schema(metas, config_props, subschema_name)
        if sc_main_discriminating_value in subschemas:
            if subschema == subschemas[sc_main_discriminating_value]:
                continue
            else:
                raise RuntimeError(f"cannot reconcile 2 schemas with same discriminating value")
        else:
            subschemas[sc_main_discriminating_value] = subschema

    if len(subschemas) == 1:
        return subschemas[subschema_name]

    UnionModel = Annotated[Union[tuple(subschemas.values())], discriminator(discriminating_fields[0], subschemas)]

    return UnionModel
