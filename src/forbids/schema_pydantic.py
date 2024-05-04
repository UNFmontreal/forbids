import pydantic
import bids
import logging
from typing import Iterator, Literal, Union, Annotated

FORBIDS_SCHEMA_FOLDER = ".forbids"


def dict2schemaprops(sidecar: dict, config_props: dict) -> Iterator:
    for k, v in sidecar.items():
        if k in config_props:
            if isinstance(config_props[k], dict):
                yield k, Annotated[sidecar2schema(v, config_props[k], k), pydantic.fields.FieldInfo(required=True)]
            else:
                yield k, (Literal[v], pydantic.fields.FieldInfo(required=True))


def sidecar2schema(sidecar: dict, config_props: dict, subschema_name: str) -> pydantic.BaseModel:
    return pydantic.create_model(
        subschema_name, __config__=pydantic.ConfigDict(extra="ignore"), **dict(dict2schemaprops(sidecar, config_props))
    )


def sidecars2unionschema(
    sidecars: list[bids.layout.BIDSJSONFile],
    bids_layout: bids.BIDSLayout,
    discriminating_fields: list[str],
    config_props: dict,
    factor_entities: list = ("subject", "session", "run"),
) -> pydantic.BaseModel:

    series_entities = [{k: v for k, v in sc.entities.items() if k not in factor_entities} for sc in sidecars]
    # TODO: not assume we have exact entities set for all sidecars
    schema_name = bids_layout.build_path(series_entities[0], absolute_paths=False)
    subschemas = {}
    for sc in sidecars:
        logging.info(f"generating schema from {sc.path}")
        metas = sc.get_dict()
        discriminating_values = [metas.get(df, "unknown") for df in discriminating_fields]
        subschema_name = schema_name + "-".join(discriminating_values)
        while subschema_name in subschemas:
            subschema_name = subschema_name + "_copy"
        subschemas[subschema_name] = sidecar2schema(metas, config_props, subschema_name)

    if len(subschemas) == 1:
        return subschemas[subschema_name]

    class UnionModel(pydantic.RootModel):
        # model_config = pydantic.ConfigDict(extra="ignore")
        root: Union[tuple(subschemas.values())] = Field(discriminator=discriminating_fields[0])

    return UnionModel
