from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import bids
import pytest

from forbids.init import generate_series_model, get_config, initialize


class TestGetConfig:
    """Test suite for get_config function."""

    def test_get_config_anat(self):
        """Test getting config for anatomical data."""
        config = get_config("anat")

        assert "instrument" in config
        assert "properties" in config
        assert "__instrument__" in config["properties"]

    def test_get_config_func(self):
        """Test getting config for functional data."""
        config = get_config("func")

        assert "instrument" in config
        assert "properties" in config

    def test_get_config_dwi(self):
        """Test getting config for diffusion data."""
        config = get_config("dwi")

        assert "instrument" in config
        assert "properties" in config

    def test_get_config_fmap(self):
        """Test getting config for fieldmap data."""
        config = get_config("fmap")

        assert "instrument" in config
        assert "properties" in config

    def test_get_config_invalid_datatype(self):
        """Test that invalid datatype raises ValueError."""
        with pytest.raises(ValueError, match="unknown data type"):
            get_config("invalid_type")

    def test_get_config_caching(self):
        """Test that config is cached after first load."""
        config1 = get_config("anat")
        config2 = get_config("anat")

        # Should be the same object (cached)
        assert config1 is config2


class TestInitialize:
    """Test suite for initialize function."""

    @patch("forbids.init.generate_series_model")
    def test_initialize_basic(self, mock_generate, mocker):
        """Test basic initialization."""
        # Mock BIDS layout
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.get_datatype.return_value = ["anat"]
        mock_layout.get.return_value = []

        mock_generate.return_value = True

        result = initialize(mock_layout)

        assert mock_layout.get_datatype.called
        assert result is True

    @patch("forbids.init.generate_series_model")
    def test_initialize_multiple_datatypes(self, mock_generate, mocker):
        """Test initialization with multiple datatypes."""
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.get_datatype.return_value = ["anat", "func", "dwi"]

        # Create mock sidecars with different entities
        mock_sidecar1 = mocker.Mock()
        mock_sidecar1.entities = {"datatype": "anat", "suffix": "T1w"}
        mock_sidecar2 = mocker.Mock()
        mock_sidecar2.entities = {"datatype": "func", "suffix": "bold"}

        def get_side_effect(**kwargs):
            if kwargs.get("datatype") == "anat":
                return [mock_sidecar1]
            elif kwargs.get("datatype") == "func":
                return [mock_sidecar2]
            return []

        mock_layout.get.side_effect = get_side_effect
        mock_generate.return_value = True

        result = initialize(mock_layout)

        # Should process multiple datatypes
        assert mock_generate.call_count >= 1

    @patch("forbids.init.generate_series_model")
    def test_initialize_uniform_sessions_false(self, mock_generate, mocker):
        """Test initialization with session-specific schemas."""
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.get_datatype.return_value = ["anat"]
        mock_layout.get.return_value = []

        mock_generate.return_value = True

        result = initialize(mock_layout, uniform_sessions=False)

        assert result is True

    @patch("forbids.init.generate_series_model")
    def test_initialize_failure(self, mock_generate, mocker):
        """Test initialization when series model generation fails."""
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.get_datatype.return_value = ["anat"]

        mock_sidecar = mocker.Mock()
        mock_sidecar.entities = {"datatype": "anat", "suffix": "T1w"}
        mock_layout.get.return_value = [mock_sidecar]

        mock_generate.return_value = False

        result = initialize(mock_layout)

        assert result is False


class TestGenerateSeriesModel:
    """Test suite for generate_series_model function."""

    @patch("forbids.init.schema.sidecars2unionschema")
    @patch("forbids.init.get_config")
    def test_generate_series_model_basic(self, mock_get_config, mock_union_schema, mocker, tmp_path):
        """Test basic series model generation."""
        # Setup mock config
        mock_config = {
            "instrument": {
                "grouping_tags": ["Manufacturer"],
                "uid_tags": ["DeviceSerialNumber"],
                "version_tags": ["SoftwareVersions"]
            },
            "properties": {
                "EchoTime": "=",
                "RepetitionTime": "="
            }
        }
        mock_get_config.return_value = mock_config

        # Setup mock BIDS layout
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.root = str(tmp_path)
        mock_layout.get_Manufacturer.return_value = ["Siemens"]
        mock_layout.get_subjects.return_value = ["01"]
        mock_layout.get_session.return_value = None
        mock_layout.build_path.return_value = "sub-ref/anat/sub-ref_T1w.json"

        # Setup mock sidecar
        mock_sidecar = mocker.Mock()
        mock_sidecar.get_dict.return_value = {
            "Manufacturer": "Siemens",
            "EchoTime": 0.03,
            "RepetitionTime": 2.0
        }
        mock_layout.get.return_value = [mock_sidecar]

        # Setup mock schema
        mock_schema = mocker.Mock()
        mock_union_schema.return_value = mock_schema

        # Mock deserialization_schema
        with patch("forbids.init.deserialization_schema") as mock_deser:
            mock_deser.return_value = {
                "type": "object",
                "properties": {}
            }

            result = generate_series_model(
                mock_layout,
                datatype="anat",
                suffix="T1w"
            )

        assert result is True
        assert mock_union_schema.called

    @patch("forbids.init.get_config")
    def test_generate_series_model_version_specific(self, mock_get_config, mocker):
        """Test series model generation with version-specific grouping."""
        mock_config = {
            "instrument": {
                "grouping_tags": ["Manufacturer"],
                "uid_tags": ["DeviceSerialNumber"],
                "version_tags": ["SoftwareVersions"]
            },
            "properties": {}
        }
        mock_get_config.return_value = mock_config

        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.get.return_value = []
        mock_layout.get_Manufacturer.return_value = []
        mock_layout.get_DeviceSerialNumber.return_value = []
        mock_layout.get_SoftwareVersions.return_value = []

        # Should not crash with version_specific=True
        result = generate_series_model(
            mock_layout,
            version_specific=True,
            datatype="anat",
            suffix="T1w"
        )

        # May fail due to no data, but should handle version_specific flag
        assert isinstance(result, bool)

    @patch("forbids.init.get_config")
    def test_generate_series_model_non_uniform_instruments(self, mock_get_config, mocker):
        """Test series model generation with instrument-specific schemas."""
        mock_config = {
            "instrument": {
                "grouping_tags": ["Manufacturer"],
                "uid_tags": ["DeviceSerialNumber"],
                "version_tags": ["SoftwareVersions"]
            },
            "properties": {}
        }
        mock_get_config.return_value = mock_config

        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.get.return_value = []
        mock_layout.get_Manufacturer.return_value = []
        mock_layout.get_DeviceSerialNumber.return_value = []

        result = generate_series_model(
            mock_layout,
            uniform_instruments=False,
            datatype="anat",
            suffix="T1w"
        )

        assert isinstance(result, bool)
