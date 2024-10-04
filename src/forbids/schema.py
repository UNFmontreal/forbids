from __future__ import annotations

import keyword
import logging
import re
from dataclasses import dataclass, make_dataclass
from typing import Annotated, Any, Iterator, Literal, NewType, Tuple, Union

import bids.layout
import jsonschema
import openapi_schema_validator.validators
from apischema import discriminator, schema
from apischema.json_schema import deserialization_schema

lgr = logging.getLogger(__name__)

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


def get_validator(sidecar_schema: dict) -> jsonschema.validators._Validator:
    # return OpenApi validator for use of discriminator feature
    validator_cls = openapi_schema_validator.validators.OAS31Validator
    validator_cls.check_schema(sidecar_schema)
    # validator_cls = jsonschema.validators.validator_for(sidecar_schema)
    return validator_cls(sidecar_schema)


def sidecars2unionschema(
    sidecars_groups: dict[Any, list[bids.layout.BIDSJSONFile]],
    bids_layout: bids.BIDSLayout,
    config_props: dict,
    series_entities: dict,
    factor_entities: tuple = ("subject", "run"),
) -> Annotated:
    # from a set of grouped sidecars from different scanners generate a meta-schema

    schema_name = bids_layout.build_path(series_entities, absolute_paths=False)[:-5] + "-"

    subschemas = []
    mapping_keys = []
    for keys, sidecars in sidecars_groups.items():
        instrument_tags = [k[0] for k in keys]
        sidecars = list(sidecars)
        # generate sidecar from first examplar
        sc = sidecars[0]
        lgr.info("generating schema from %s", sc.relpath)
        metas = prepare_metadata(sc, instrument_tags)
        mapping_keys.append(metas["__instrument__"])
        subschema_name = schema_name + "".join([k.replace(".", "") for t, k in keys])
        subschema_name = subschema_name.replace("_", "").replace("-", "")
        # while subschema_name in subschemas:
        #    subschema_name = subschema_name + "_copy"
        subschema = sidecar2schema(metas, config_props, subschema_name)
        # check if we can apply the schema from 1st sidecar to the others:
        validator = get_validator(deserialization_schema(subschema, additional_properties=True))
        for sidecar in sidecars[1:]:
            lgr.info("validating schema from %s", sidecar.relpath)
            # validate or raise
            validator.validate(prepare_metadata(sidecar, instrument_tags))

        subschemas.append(subschema)

    # if homogeneous (eg. single-site or single-vendor)
    if len(subschemas) == 1:
        return subschemas[0]

    UnionModel = Annotated[
        Union[tuple(subschemas)],
        discriminator(
            "__instrument__",
            #            {k :sc.__name__ for k, sc in zip(mapping_keys, subschemas)}
        ),
    ]

    return UnionModel


def compare_schema(sc1: dataclass, sc2: dataclass) -> bool:
    # compares 2 dataclasses, not really useful now
    match = True

    sc1_props = sc1.__dataclass_fields__
    sc2_props = sc2.__dataclass_fields__
    sc1_props_keys = set(sc1_props.keys())
    sc2_props_keys = set(sc2_props.keys())
    lgr.debug("XOR: %s", str(set(sc1_props_keys).symmetric_difference(sc2_props_keys)))
    for prop in sc1_props_keys.intersection(sc2_props_keys):
        if isinstance(sc1_props[prop], type):
            match = compare_schema(sc1_props[prop], sc2_props[prop])
        t1, t2 = sc1_props[prop].type, sc2_props[prop].type
        if t1 != t2:
            if not hasattr(t1, "__supertype__") or t1.__supertype__ != t2.__supertype__:
                lgr.debug(str((prop, sc1_props[prop].type, sc2_props[prop].type)))
                match = False
    return match


def prepare_metadata(
    sidecar,
    instrument_tags,
):
    # prepares sidecar data for use with json_schema

    # rename conflictual keywords as the schema was created
    sidecar_data = {k + ("__" if k in keyword.kwlist else ""): v for k, v in sidecar.get_dict().items()}
    # create an aggregate tag of all schema-defined instrument tags
    sidecar_data["__instrument__"] = "-".join([sidecar_data.get(instr_tag, "unknown") for instr_tag in instrument_tags])
    return sidecar_data
