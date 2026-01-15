"""Schema generation and validation module for forBIDS.

This module provides functionality to generate JSON schemas from exemplar BIDS data
and validate BIDS datasets against protocol compliance schemas. It supports multi-site
and multi-vendor studies by allowing conditional schema constraints based on scanner
manufacturer, model, and software version.
"""
from __future__ import annotations

import keyword
import logging
import os
import re
from dataclasses import dataclass, make_dataclass
from typing import (Annotated, Any, Dict, Iterator, Literal, NewType, Tuple,
                    Union)

import bids.layout
import jsonschema
import openapi_schema_validator.validators
from apischema import discriminator, schema
from apischema.json_schema import deserialization_schema

lgr = logging.getLogger(__name__)
DEBUG = bool(os.environ.get("DEBUG", False))
lgr.setLevel(logging.DEBUG if DEBUG else logging.INFO)

FORBIDS_SCHEMA_FOLDER = ".forbids"

# entities that differentiate files from the same series
# where it might be None for one of the files.
ALT_ENTITIES = ["reconstruction", "acquisition"]


def tagpreset2type(tag: str, tag_preset: str, value: Any):
    """Convert tag presets from config files into typed constraints.

    This function creates Python types with validation constraints based on preset
    expressions. Supported presets:
    - "=" : Exact equality (Literal type)
    - "*" : Any value of the same type (wildcard)
    - "~=X" : Tolerance constraint (value ± X)
    - "rPATTERN" : Regex pattern matching

    Args:
        tag: The name of the metadata tag.
        tag_preset: The constraint expression (e.g., "=", "*", "~=0.05", "r^[A-Z]+$").
        value: The exemplar value used to determine type and set constants.

    Returns:
        A Python type with apischema validation constraints applied.

    Raises:
        RuntimeError: If the tag_preset is not a supported constraint type.

    Examples:
        >>> tagpreset2type("EchoTime", "=", 0.03)
        Literal[0.03]
        >>> tagpreset2type("Manufacturer", "*", "Siemens")
        <class 'str'>
        >>> tagpreset2type("FlipAngle", "~=1.0", 90.0)
        NewType('FlipAngle', float)  # with min=89.0, max=91.0
    """
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


def struct2schemaprops(sidecar: dict, config_props: dict, schema_path: str) -> Iterator:
    """Generate dataclass field definitions from exemplar data and config.

    Recursively processes a sidecar dictionary and configuration to create typed
    field definitions suitable for dataclass creation. Handles nested structures
    and renames Python keywords by appending "__".

    Args:
        sidecar: Dictionary with exemplar values to determine types and constants.
        config_props: Dictionary with validation presets for each property.
        schema_path: Schema name prefix for recursive schema definitions (ensures uniqueness).

    Yields:
        Tuples of (field_name, field_type) for dataclass field definitions.

    Examples:
        >>> sidecar = {"EchoTime": 0.03, "Manufacturer": "Siemens"}
        >>> config = {"EchoTime": "=", "Manufacturer": "*"}
        >>> list(struct2schemaprops(sidecar, config, "T1w"))
        [('EchoTime', Literal[0.03]), ('Manufacturer', <class 'str'>)]
    """
    for k, tag_preset in config_props.items():
        if k in sidecar:
            v = sidecar[k]
            k2 = k + ("__" if k in keyword.kwlist else "")
            if isinstance(config_props[k], dict):
                yield k2, sidecar2schema(v, tag_preset, f"{schema_path}_{k}")
            elif isinstance(config_props[k], list):
                yield k2, sidecar2schema(v, tag_preset, f"{schema_path}_{k}")
            else:
                yield k2, tagpreset2type(f"{schema_path}_{k}", tag_preset, v)


def sidecar2schema(sidecar: dict, config_props: dict, subschema_name: str):
    """Generate a dataclass schema from an exemplar sidecar and configuration.

    Creates a dataclass with typed fields based on the exemplar sidecar data
    and validation configuration.

    Args:
        sidecar: Exemplar sidecar dictionary with metadata values.
        config_props: Schema properties configuration with validation presets.
        subschema_name: Name to assign to the generated dataclass.

    Returns:
        A dynamically created dataclass type with validated fields.

    Examples:
        >>> sidecar = {"EchoTime": 0.03}
        >>> config = {"EchoTime": "="}
        >>> schema = sidecar2schema(sidecar, config, "T1wSchema")
        >>> schema.__name__
        'T1wSchema'
    """
    return make_dataclass(subschema_name, fields=list(struct2schemaprops(sidecar, config_props, subschema_name)))


def get_validator(sidecar_schema: dict) -> jsonschema.validators._Validator:
    """Create an OpenAPI 3.1 validator for the given schema.

    Returns a validator that supports OpenAPI discriminator features,
    which are used for multi-vendor schema validation.

    Args:
        sidecar_schema: JSON schema dictionary to validate against.

    Returns:
        An OAS31Validator instance configured for the schema.

    Raises:
        jsonschema.exceptions.SchemaError: If the schema is invalid.
    """
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
    """Generate a union schema from grouped sidecars across different scanners.

    Creates a meta-schema that can validate data from multiple scanner configurations
    using discriminated unions based on instrument tags (manufacturer, model, etc.).

    Args:
        sidecars_groups: Dictionary mapping instrument tag tuples to lists of sidecars.
        bids_layout: BIDS layout object for the dataset.
        config_props: Schema properties configuration.
        series_entities: BIDS entities identifying the series (e.g., datatype, suffix).
        factor_entities: Entities to factor out (default: subject, run).

    Returns:
        An Annotated union type with discriminator for multi-vendor validation.

    Raises:
        ValidationError: If sidecars within a group don't match the generated schema.
    """

    schema_name = bids_layout.build_path(series_entities, absolute_paths=False)[:-5] + "-"

    subschemas = []
    mapping_keys = []
    for keys, sidecars in sidecars_groups.items():
        instrument_tags = [k[0] for k in keys]
        sidecars = list(sidecars)
        # generate schema from first examplar
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

#    # if homogeneous (eg. single-site or single-vendor)
#    if len(subschemas) == 1:
#        return subschemas[0]

    UnionModel = Annotated[
        Union[tuple(subschemas)],
        discriminator(
            "__instrument__",
            #            {k :sc.__name__ for k, sc in zip(mapping_keys, subschemas)}
        ),
    ]
    print(UnionModel)

    return UnionModel


def compare_schema(sc1: dataclass, sc2: dataclass) -> bool:
    """Compare two dataclass schemas for structural equality.

    Recursively compares field names and types between two dataclass schemas.
    Note: This function is currently not actively used in the codebase.

    Args:
        sc1: First dataclass to compare.
        sc2: Second dataclass to compare.

    Returns:
        True if schemas match, False otherwise.
    """
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


def get_instrument_key(
    sidecar_data: dict[str, Any],
    instrument_tags: List[str],
):
    """Compose an instrument key from metadata and tag list.

    Creates a unique identifier for scanner configurations by joining
    instrument tag values with hyphens. Missing tags default to "unknown".

    Args:
        sidecar_data: Metadata dictionary containing instrument information.
        instrument_tags: List of tag names to include in the key (e.g., ["Manufacturer", "ManufacturersModelName"]).

    Returns:
        A hyphen-separated string key (e.g., "Siemens-Prisma-VE11C").

    Examples:
        >>> data = {"Manufacturer": "Siemens", "ManufacturersModelName": "Prisma"}
        >>> get_instrument_key(data, ["Manufacturer", "ManufacturersModelName"])
        'Siemens-Prisma'
    """
    return "-".join([sidecar_data.get(instr_tag, "unknown") for instr_tag in instrument_tags])


def prepare_metadata(
    sidecar: bids.layout.BIDSJSONFile,
    instrument_tags: List[str],
):
    """Prepare sidecar metadata for JSON schema validation.

    Processes BIDS sidecar data by:
    1. Renaming Python keywords (e.g., "class" -> "class__")
    2. Adding an "__instrument__" key with the composite instrument identifier

    Args:
        sidecar: BIDS JSON sidecar file object.
        instrument_tags: List of tag names to use for instrument identification.

    Returns:
        Dictionary with processed metadata ready for schema validation.

    Examples:
        >>> # Assuming sidecar contains {"Manufacturer": "Siemens", "class": "MR"}
        >>> prepare_metadata(sidecar, ["Manufacturer"])
        {"Manufacturer": "Siemens", "class__": "MR", "__instrument__": "Siemens"}
    """

    # rename conflictual keywords as the schema was created
    sidecar_data = {k + ("__" if k in keyword.kwlist else ""): v for k, v in sidecar.get_dict().items()}
    # create an aggregate tag of all schema-defined instrument tags
    sidecar_data["__instrument__"] = get_instrument_key(sidecar_data, instrument_tags)
    return sidecar_data
