from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from forbids.cli.run import main, parse_args


class TestParseArgs:
    """Test suite for parse_args function."""

    def test_parse_args_init(self):
        """Test parsing init command arguments."""
        test_args = ["forbids", "init", "/path/to/bids"]
        with patch.object(sys, "argv", test_args):
            args = parse_args()

            assert args.command == "init"
            assert args.bids_path == "/path/to/bids"
            assert args.session_specific is False
            assert args.scanner_specific is False
            assert args.version_specific is False

    def test_parse_args_validate(self):
        """Test parsing validate command arguments."""
        test_args = ["forbids", "validate", "/path/to/bids"]
        with patch.object(sys, "argv", test_args):
            args = parse_args()

            assert args.command == "validate"
            assert args.bids_path == "/path/to/bids"

    def test_parse_args_init_with_flags(self):
        """Test parsing init command with optional flags."""
        test_args = [
            "forbids", "init", "/path/to/bids",
            "--session-specific",
            "--scanner-specific",
            "--version-specific"
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_args()

            assert args.session_specific is True
            assert args.scanner_specific is True
            assert args.version_specific is True

    def test_parse_args_validate_with_participant(self):
        """Test parsing validate command with participant label."""
        test_args = [
            "forbids", "validate", "/path/to/bids",
            "--participant-label", "01", "02"
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_args()

            assert args.participant_label == ["01", "02"]

    def test_parse_args_validate_with_session(self):
        """Test parsing validate command with session label."""
        test_args = [
            "forbids", "validate", "/path/to/bids",
            "--session-label", "01"
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_args()

            assert args.session_label == ["01"]


class TestMain:
    """Test suite for main function."""

    @patch("forbids.cli.run.initialize")
    @patch("forbids.cli.run.bids.BIDSLayout")
    def test_main_init_success(self, mock_bids_layout, mock_initialize):
        """Test main function with init command success."""
        test_args = ["forbids", "init", "/path/to/bids"]

        mock_initialize.return_value = True

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0
            assert mock_initialize.called

    @patch("forbids.cli.run.initialize")
    @patch("forbids.cli.run.bids.BIDSLayout")
    def test_main_init_failure(self, mock_bids_layout, mock_initialize):
        """Test main function with init command failure."""
        test_args = ["forbids", "init", "/path/to/bids"]

        mock_initialize.return_value = False

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1

    @patch("forbids.cli.run.process_validation")
    @patch("forbids.cli.run.bids.BIDSLayout")
    def test_main_validate_success(self, mock_bids_layout, mock_process_validation):
        """Test main function with validate command success."""
        test_args = [
            "forbids", "validate", "/path/to/bids",
            "--participant-label", "01"
        ]

        mock_process_validation.return_value = True

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0
            assert mock_process_validation.called

    @patch("forbids.cli.run.process_validation")
    @patch("forbids.cli.run.bids.BIDSLayout")
    def test_main_validate_failure(self, mock_bids_layout, mock_process_validation):
        """Test main function with validate command failure."""
        test_args = [
            "forbids", "validate", "/path/to/bids",
            "--participant-label", "01"
        ]

        mock_process_validation.return_value = False

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1

    @patch("forbids.cli.run.initialize")
    @patch("forbids.cli.run.bids.BIDSLayout")
    def test_main_init_with_options(self, mock_bids_layout, mock_initialize):
        """Test main function with init command and options."""
        test_args = [
            "forbids", "init", "/path/to/bids",
            "--session-specific",
            "--scanner-specific",
            "--version-specific"
        ]

        mock_initialize.return_value = True

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Verify initialize was called with correct parameters
            mock_initialize.assert_called_once()
            call_kwargs = mock_initialize.call_args[1]
            assert call_kwargs["uniform_sessions"] is False
            assert call_kwargs["uniform_instruments"] is False
            assert call_kwargs["version_specific"] is True

    @patch("forbids.cli.run.process_validation")
    @patch("forbids.cli.run.bids.BIDSLayout")
    def test_main_validate_with_session(self, mock_bids_layout, mock_process_validation):
        """Test main function with validate command and session."""
        test_args = [
            "forbids", "validate", "/path/to/bids",
            "--participant-label", "01",
            "--session-label", "baseline"
        ]

        mock_process_validation.return_value = True

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Verify process_validation was called with correct parameters
            mock_process_validation.assert_called_once()
            call_kwargs = mock_process_validation.call_args[1]
            assert call_kwargs["subject"] == ["01"]
            assert call_kwargs["session"] == ["baseline"]
