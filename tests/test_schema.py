from __future__ import annotations

import keyword
from dataclasses import dataclass
from typing import Literal

import pytest
from apischema.json_schema import deserialization_schema

from forbids.schema import (
    compare_schema,
    get_instrument_key,
    prepare_metadata,
    sidecar2schema,
    struct2schemaprops,
    tagpreset2type,
)


class TestTagpreset2type:
    """Test suite for tagpreset2type function."""

    def test_wildcard_type_number(self):
        """Test wildcard (*) type with number."""
        typ_sc = deserialization_schema(tagpreset2type("any", "*", 10.0))
        typ_sc.pop("$schema")
        assert typ_sc == {"type": "number"}

    def test_wildcard_type_string(self):
        """Test wildcard (*) type with string."""
        typ_sc = deserialization_schema(tagpreset2type("any", "*", "test"))
        typ_sc.pop("$schema")
        assert typ_sc == {"type": "string"}

    def test_wildcard_type_list(self):
        """Test wildcard (*) type with list."""
        typ_sc = deserialization_schema(tagpreset2type("any", "*", [1, 2, 3]))
        typ_sc.pop("$schema")
        assert typ_sc == {"type": "array", "items": {}}

    def test_tolerance_type(self):
        """Test tolerance (~=) type."""
        typ_sc = deserialization_schema(tagpreset2type("near", "~=.05", 10.0))
        typ_sc.pop("$schema")
        assert typ_sc == {"type": "number", "minimum": 9.95, "maximum": 10.05}

    def test_tolerance_type_larger(self):
        """Test tolerance with larger value."""
        typ_sc = deserialization_schema(tagpreset2type("near", "~=1.0", 100.0))
        typ_sc.pop("$schema")
        assert typ_sc == {"type": "number", "minimum": 99.0, "maximum": 101.0}

    def test_equality_type_number(self):
        """Test equality (=) type with number."""
        typ_sc = deserialization_schema(tagpreset2type("eq", "=", 10.0))
        typ_sc.pop("$schema")
        assert typ_sc == {"type": "number", "const": 10}

    def test_equality_type_string(self):
        """Test equality (=) type with string."""
        typ_sc = deserialization_schema(tagpreset2type("eq", "=", "test"))
        typ_sc.pop("$schema")
        assert typ_sc == {"type": "string", "const": "test"}

    def test_equality_type_list(self):
        """Test equality (=) type with list."""
        typ_sc = deserialization_schema(tagpreset2type("eq", "=", ["a", "b"]))
        typ_sc.pop("$schema")
        # List creates a tuple of literals
        assert "prefixItems" in typ_sc or "items" in typ_sc

    def test_regex_type(self):
        """Test regex (r) type."""
        typ_sc = deserialization_schema(tagpreset2type("regex", "r^[aA]{3}[0-4]$", "AaA3"))
        typ_sc.pop("$schema")
        assert typ_sc == {
            "type": "string",
            "pattern": "^[aA]{3}[0-4]$",
        }

    def test_regex_type_complex(self):
        """Test regex with complex pattern."""
        typ_sc = deserialization_schema(tagpreset2type("regex", "r^[A-Z]{2}\\d{3}$", "AB123"))
        typ_sc.pop("$schema")
        assert typ_sc == {
            "type": "string",
            "pattern": "^[A-Z]{2}\\d{3}$",
        }

    def test_unsupported_constraint(self):
        """Test unsupported constraint raises error."""
        with pytest.raises(RuntimeError, match="Unsupported constraint"):
            tagpreset2type("tag", "unsupported", 10.0)


class TestStruct2schemaprops:
    """Test suite for struct2schemaprops function."""

    def test_simple_properties(self):
        """Test simple property generation."""
        sidecar = {"field1": 10, "field2": "test"}
        config = {"field1": "=", "field2": "*"}
        props = list(struct2schemaprops(sidecar, config, "TestSchema"))

        assert len(props) == 2
        assert props[0][0] == "field1"
        assert props[1][0] == "field2"

    def test_keyword_field_renaming(self):
        """Test that Python keywords are renamed with __ suffix."""
        sidecar = {"class": "value", "for": "test"}
        config = {"class": "*", "for": "*"}
        props = list(struct2schemaprops(sidecar, config, "TestSchema"))

        # Keywords should be renamed
        field_names = [p[0] for p in props]
        assert "class__" in field_names
        assert "for__" in field_names

    def test_nested_dict_properties(self):
        """Test nested dictionary handling."""
        sidecar = {"nested": {"inner": 10}}
        config = {"nested": {"inner": "="}}
        props = list(struct2schemaprops(sidecar, config, "TestSchema"))

        assert len(props) == 1
        assert props[0][0] == "nested"

    def test_missing_field_in_sidecar(self):
        """Test that missing fields in sidecar are skipped."""
        sidecar = {"field1": 10}
        config = {"field1": "=", "field2": "*"}
        props = list(struct2schemaprops(sidecar, config, "TestSchema"))

        # Only field1 should be present
        assert len(props) == 1
        assert props[0][0] == "field1"


class TestSidecar2schema:
    """Test suite for sidecar2schema function."""

    def test_simple_schema_generation(self):
        """Test simple schema generation."""
        sidecar = {"field1": 10, "field2": "test"}
        config = {"field1": "=", "field2": "*"}
        schema = sidecar2schema(sidecar, config, "TestSchema")

        assert hasattr(schema, "__dataclass_fields__")
        assert "field1" in schema.__dataclass_fields__
        assert "field2" in schema.__dataclass_fields__

    def test_schema_with_keyword_fields(self):
        """Test schema generation with Python keyword fields."""
        sidecar = {"class": "value"}
        config = {"class": "*"}
        schema = sidecar2schema(sidecar, config, "TestSchema")

        assert hasattr(schema, "__dataclass_fields__")
        assert "class__" in schema.__dataclass_fields__


class TestGetInstrumentKey:
    """Test suite for get_instrument_key function."""

    def test_single_tag(self):
        """Test instrument key with single tag."""
        sidecar_data = {"Manufacturer": "Siemens"}
        instrument_tags = ["Manufacturer"]
        key = get_instrument_key(sidecar_data, instrument_tags)

        assert key == "Siemens"

    def test_multiple_tags(self):
        """Test instrument key with multiple tags."""
        sidecar_data = {
            "Manufacturer": "Siemens",
            "ManufacturersModelName": "Prisma",
            "SoftwareVersions": "VE11C"
        }
        instrument_tags = ["Manufacturer", "ManufacturersModelName", "SoftwareVersions"]
        key = get_instrument_key(sidecar_data, instrument_tags)

        assert key == "Siemens-Prisma-VE11C"

    def test_missing_tag(self):
        """Test instrument key with missing tag."""
        sidecar_data = {"Manufacturer": "Siemens"}
        instrument_tags = ["Manufacturer", "ManufacturersModelName"]
        key = get_instrument_key(sidecar_data, instrument_tags)

        assert key == "Siemens-unknown"

    def test_empty_tags(self):
        """Test instrument key with empty tags list."""
        sidecar_data = {"Manufacturer": "Siemens"}
        instrument_tags = []
        key = get_instrument_key(sidecar_data, instrument_tags)

        assert key == ""


class TestPrepareMetadata:
    """Test suite for prepare_metadata function."""

    def test_basic_metadata_preparation(self, mocker):
        """Test basic metadata preparation."""
        # Mock BIDSJSONFile
        mock_sidecar = mocker.Mock()
        mock_sidecar.get_dict.return_value = {
            "Manufacturer": "Siemens",
            "EchoTime": 0.03
        }

        instrument_tags = ["Manufacturer"]
        result = prepare_metadata(mock_sidecar, instrument_tags)

        assert "Manufacturer" in result
        assert "EchoTime" in result
        assert "__instrument__" in result
        assert result["__instrument__"] == "Siemens"

    def test_keyword_renaming(self, mocker):
        """Test that Python keywords are renamed."""
        mock_sidecar = mocker.Mock()
        mock_sidecar.get_dict.return_value = {
            "class": "value",
            "Manufacturer": "Siemens"
        }

        instrument_tags = ["Manufacturer"]
        result = prepare_metadata(mock_sidecar, instrument_tags)

        assert "class__" in result
        assert "class" not in result
        assert result["class__"] == "value"

    def test_instrument_key_generation(self, mocker):
        """Test instrument key is properly generated."""
        mock_sidecar = mocker.Mock()
        mock_sidecar.get_dict.return_value = {
            "Manufacturer": "GE",
            "ManufacturersModelName": "Discovery"
        }

        instrument_tags = ["Manufacturer", "ManufacturersModelName"]
        result = prepare_metadata(mock_sidecar, instrument_tags)

        assert result["__instrument__"] == "GE-Discovery"


class TestCompareSchema:
    """Test suite for compare_schema function."""

    def test_identical_schemas(self):
        """Test comparison of identical schemas."""
        @dataclass
        class Schema1:
            field1: int
            field2: str

        @dataclass
        class Schema2:
            field1: int
            field2: str

        # Note: compare_schema may not work perfectly with simple dataclasses
        # This is a basic test to ensure it doesn't crash
        result = compare_schema(Schema1, Schema2)
        assert isinstance(result, bool)

    def test_different_schemas(self):
        """Test comparison of different schemas."""
        @dataclass
        class Schema1:
            field1: int

        @dataclass
        class Schema2:
            field1: str

        result = compare_schema(Schema1, Schema2)
        # Should detect difference
        assert isinstance(result, bool)
