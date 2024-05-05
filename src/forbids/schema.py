import keyword
import bids.layout
import logging
from typing import Annotated, Literal, Union, Tuple, Iterator
from dataclasses import asdict, dataclass, make_dataclass, field
from apischema import discriminator
from collections.abc import Sequence


FORBIDS_SCHEMA_FOLDER = ".forbids"


# entities that differentiate files from the same series
# where it might be None for one of the files.
ALT_ENTITIES = ["reconstruction"]


def dict2schemaprops(sidecar: dict, config_props: dict) -> Iterator:
    for k, v in sidecar.items():
        if k in config_props:
            k2 = k + ("__" if k in keyword.kwlist else "")
            if isinstance(config_props[k], dict):
                yield k2, sidecar2schema(v, config_props[k], k), field()
            elif isinstance(v, list):
                yield k2, Tuple[*[Literal[vv] for vv in v]], field()
            else:
                yield k2, Literal[v], field()


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
        discriminating_values = [metas.get(df) for df in discriminating_fields if df in metas]
        subschema_name = schema_name + "-".join(discriminating_values)
        while subschema_name in subschemas:
            subschema_name = subschema_name + "_copy"
        subschemas[subschema_name] = sidecar2schema(metas, config_props, subschema_name)

    if len(subschemas) == 1:
        return subschemas[subschema_name]

    UnionModel = Annotated[Union[tuple(subschemas.values())], discriminator(discriminating_fields[0], subschemas)]

    return UnionModel