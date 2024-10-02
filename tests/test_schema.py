from __future__ import annotations

from apischema.json_schema import deserialization_schema

from forbids.schema import tagpreset2type


def test_tagpreset2type():
    typ_sc = deserialization_schema(tagpreset2type("any", "*", 10.0))
    typ_sc.pop("$schema")
    assert typ_sc == {"type": "number"}

    typ_sc = deserialization_schema(tagpreset2type("near", "~=.05", 10.0))
    typ_sc.pop("$schema")
    assert typ_sc == {"type": "number", "minimum": 9.95, "maximum": 10.05}

    typ_sc = deserialization_schema(tagpreset2type("eq", "=", 10.0))
    typ_sc.pop("$schema")
    assert typ_sc == {"type": "number", "const": 10}

    typ_sc = deserialization_schema(tagpreset2type("regex", "r^[aA]{3}[0-4]$", "AaA3"))
    typ_sc.pop("$schema")
    assert typ_sc == {
        "type": "string",
        "pattern": "^[aA]{3}[0-4]$",
    }


def test_dict2schemaprops():
    pass
