from __future__ import annotations

import logging
from unittest.mock import Mock, patch

import bids
import pytest
from jsonschema.exceptions import ValidationError

from forbids.validation import (
    BIDSFileError,
    BIDSJSONError,
    add_path_note_to_error,
    process_validation,
    validate,
)


class TestBIDSJSONError:
    """Test suite for BIDSJSONError class."""

    def test_bidsjson_error_creation(self):
        """Test BIDSJSONError can be created."""
        error = BIDSJSONError("Test error message")
        assert isinstance(error, ValidationError)
        assert str(error) == "Test error message"

    def test_bidsjson_error_inheritance(self):
        """Test BIDSJSONError inherits from ValidationError."""
        error = BIDSJSONError("Test")
        assert isinstance(error, ValidationError)


class TestBIDSFileError:
    """Test suite for BIDSFileError class."""

    def test_bidsfile_error_creation(self):
        """Test BIDSFileError can be created."""
        error = BIDSFileError("Missing file")
        assert isinstance(error, ValidationError)
        assert str(error) == "Missing file"

    def test_bidsfile_error_inheritance(self):
        """Test BIDSFileError inherits from ValidationError."""
        error = BIDSFileError("Test")
        assert isinstance(error, ValidationError)


class TestAddPathNoteToError:
    """Test suite for add_path_note_to_error function."""

    def test_add_path_note_to_error(self, mocker):
        """Test adding path notes to validation errors."""
        # Create a mock validator that yields errors
        mock_validator = mocker.Mock()
        mock_error = ValidationError("Test error")
        mock_validator.iter_errors.return_value = [mock_error]

        sidecar_data = {"field": "value"}
        filepath = "sub-01/anat/sub-01_T1w.json"

        errors = list(add_path_note_to_error(mock_validator, sidecar_data, filepath))

        assert len(errors) == 1
        assert errors[0] is mock_error
        assert hasattr(errors[0], "__notes__")
        assert filepath in errors[0].__notes__

    def test_add_path_note_multiple_errors(self, mocker):
        """Test adding path notes to multiple errors."""
        mock_validator = mocker.Mock()
        error1 = ValidationError("Error 1")
        error2 = ValidationError("Error 2")
        mock_validator.iter_errors.return_value = [error1, error2]

        filepath = "sub-01/anat/sub-01_T1w.json"
        errors = list(add_path_note_to_error(mock_validator, {}, filepath))

        assert len(errors) == 2
        for error in errors:
            assert filepath in error.__notes__


class TestValidate:
    """Test suite for validate function."""

    @patch("forbids.validation.schema.get_validator")
    @patch("forbids.validation.schema.get_instrument_key")
    @patch("forbids.validation.bids.BIDSLayout")
    def test_validate_basic(self, mock_bids_layout_cls, mock_get_key, mock_get_validator, mocker):
        """Test basic validation."""
        # Setup main layout
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.root = "/data/bids"
        mock_layout.get_subject.return_value = ["01"]
        mock_layout.get_session.return_value = []

        # Setup reference layout
        mock_ref_layout = mocker.Mock()
        mock_ref_sidecar = mocker.Mock()
        mock_ref_sidecar.relpath = "sub-ref/anat/sub-ref_T1w.json"
        mock_ref_sidecar.entities = {"datatype": "anat", "suffix": "T1w"}
        mock_ref_sidecar.get_dict.return_value = {
            "bids": {
                "instrument_tags": ["Manufacturer"],
                "optional": False,
                "required_for_instruments": ["Siemens"],
                "min_runs": 1,
                "max_runs": 1
            },
            "EchoTime": 0.03
        }
        mock_ref_layout.get.return_value = [mock_ref_sidecar]
        mock_ref_layout.get_session.return_value = []

        mock_bids_layout_cls.return_value = mock_ref_layout

        # Setup data sidecar
        mock_data_sidecar = mocker.Mock()
        mock_data_sidecar.relpath = "sub-01/anat/sub-01_T1w.json"

        def layout_get(**kwargs):
            if kwargs.get("extension") == ".json" and "subject" in kwargs:
                return [mock_data_sidecar]
            return []

        mock_layout.get.side_effect = layout_get
        mock_layout.get_Manufacturer.return_value = ["Siemens"]
        mock_layout.build_path.return_value = "sub-01/anat/sub-01_T1w.json"

        # Setup validator
        mock_validator = mocker.Mock()
        mock_validator.iter_errors.return_value = []
        mock_get_validator.return_value = mock_validator

        mock_get_key.return_value = "Siemens"

        # Run validation
        errors = list(validate(mock_layout, subject="01", session=None))

        # Should have no errors for valid data
        assert len(errors) == 0

    @patch("forbids.validation.schema.get_validator")
    @patch("forbids.validation.schema.get_instrument_key")
    @patch("forbids.validation.bids.BIDSLayout")
    def test_validate_missing_required_file(self, mock_bids_layout_cls, mock_get_key, mock_get_validator, mocker):
        """Test validation detects missing required files."""
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.root = "/data/bids"
        mock_layout.get_subject.return_value = ["01"]
        mock_layout.get_session.return_value = []

        # Setup reference layout with required file
        mock_ref_layout = mocker.Mock()
        mock_ref_sidecar = mocker.Mock()
        mock_ref_sidecar.relpath = "sub-ref/anat/sub-ref_T1w.json"
        mock_ref_sidecar.entities = {"datatype": "anat", "suffix": "T1w"}
        mock_ref_sidecar.get_dict.return_value = {
            "bids": {
                "instrument_tags": ["Manufacturer"],
                "optional": False,
                "required_for_instruments": ["Siemens"],
                "min_runs": 1,
                "max_runs": 1
            }
        }
        mock_ref_layout.get.return_value = [mock_ref_sidecar]
        mock_ref_layout.get_session.return_value = []

        mock_bids_layout_cls.return_value = mock_ref_layout

        # No matching sidecars in data
        mock_layout.get.return_value = []
        mock_layout.get_Manufacturer.return_value = ["Siemens"]
        mock_layout.build_path.return_value = "sub-01/anat/sub-01_T1w.json"

        mock_get_key.return_value = "Siemens"

        # Run validation
        errors = list(validate(mock_layout, subject="01", session=None))

        # Should detect missing required file
        assert len(errors) > 0
        assert any(isinstance(e, BIDSFileError) for e in errors)

    @patch("forbids.validation.schema.get_validator")
    @patch("forbids.validation.bids.BIDSLayout")
    def test_validate_optional_file_missing(self, mock_bids_layout_cls, mock_get_validator, mocker):
        """Test validation allows missing optional files."""
        mock_layout = mocker.Mock(spec=bids.BIDSLayout)
        mock_layout.root = "/data/bids"
        mock_layout.get_subject.return_value = ["01"]
        mock_layout.get_session.return_value = []

        # Setup reference layout with optional file
        mock_ref_layout = mocker.Mock()
        mock_ref_sidecar = mocker.Mock()
        mock_ref_sidecar.relpath = "sub-ref/anat/sub-ref_FLAIR.json"
        mock_ref_sidecar.entities = {"datatype": "anat", "suffix": "FLAIR"}
        mock_ref_sidecar.get_dict.return_value = {
            "bids": {
                "instrument_tags": [],
                "optional": True,
                "required_for_instruments": [],
                "min_runs": 0,
                "max_runs": 1
            }
        }
        mock_ref_layout.get.return_value = [mock_ref_sidecar]
        mock_ref_layout.get_session.return_value = []

        mock_bids_layout_cls.return_value = mock_ref_layout

        # No matching sidecars in data (but it's optional)
        mock_layout.get.return_value = []

        # Run validation
        errors = list(validate(mock_layout, subject="01", session=None))

        # Should not report error for missing optional file
        assert len(errors) == 0


class TestProcessValidation:
    """Test suite for process_validation function."""

    @patch("forbids.validation.validate")
    def test_process_validation_success(self, mock_validate, mocker):
        """Test process_validation with no errors."""
        mock_layout = mocker.Mock()
        mock_validate.return_value = []

        result = process_validation(mock_layout, subject="01", session=None)

        assert result is True
        assert mock_validate.called

    @patch("forbids.validation.validate")
    def test_process_validation_with_errors(self, mock_validate, mocker, caplog):
        """Test process_validation with validation errors."""
        mock_layout = mocker.Mock()

        error = BIDSFileError("Missing file")
        error.add_note("sub-01/anat/sub-01_T1w.json")
        mock_validate.return_value = [error]

        with caplog.at_level(logging.ERROR):
            result = process_validation(mock_layout, subject="01", session=None)

        assert result is False
        assert "Missing file" in caplog.text

    @patch("forbids.validation.validate")
    def test_process_validation_multiple_errors(self, mock_validate, mocker, caplog):
        """Test process_validation with multiple errors."""
        mock_layout = mocker.Mock()

        error1 = BIDSFileError("Missing file 1")
        error1.add_note("sub-01/anat/sub-01_T1w.json")
        error2 = BIDSJSONError("Invalid metadata")
        error2.add_note("sub-01/func/sub-01_bold.json")

        mock_validate.return_value = [error1, error2]

        with caplog.at_level(logging.ERROR):
            result = process_validation(mock_layout, subject="01", session=None)

        assert result is False
        # Should log both errors
        assert "Missing file 1" in caplog.text or "Invalid metadata" in caplog.text
