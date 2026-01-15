"""Command-line interface for forBIDS.

This module provides the CLI entry point for forBIDS, supporting two main commands:
- init: Initialize schemas from a BIDS dataset
- validate: Validate a BIDS dataset against existing schemas
"""
from __future__ import annotations

import argparse
import logging
import os

import bids
import coloredlogs

from ..init import initialize
from ..validation import process_validation

DEBUG = bool(os.environ.get("DEBUG", False))
coloredlogs.install()
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    logging.root.setLevel(logging.DEBUG)
    root_handler = logging.root.handlers[0]
    root_handler.setFormatter(
        logging.Formatter("%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s")
    )
else:
    root_handler = logging.root.handlers[0]
    root_handler.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    logging.root.setLevel(logging.INFO)

lgr = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for forBIDS.

    Returns:
        Parsed arguments namespace containing:
            - command: "init" or "validate"
            - bids_path: Path to BIDS dataset
            - session_specific: Whether to create session-specific schemas (init only)
            - scanner_specific: Whether to create scanner-specific schemas (init only)
            - version_specific: Whether to create version-specific schemas (init only)
            - participant_label: List of participant IDs to validate (validate only)
            - session_label: List of session IDs to validate (validate only)

    Examples:
        >>> # From command line:
        >>> # forbids init /data/bids --session-specific
        >>> # forbids validate /data/bids --participant-label 01 02
    """

    p = argparse.ArgumentParser(description="forbids - setup and validate protocol compliance")
    p.add_argument("command", help="init or validate")
    p.add_argument("bids_path", help="path to the BIDS dataset")
    p.add_argument(
        "--session-specific",
        action="store_true",
        default=False,
        help="build a different schema for each session, is the study design is not repeated measures",
    )

    p.add_argument(
        "--scanner-specific",
        action="store_true",
        default=False,
        help="allow schema to be scanner instance specific",
    )
    p.add_argument(
        "--version-specific",
        action="store_true",
        default=False,
        help="allow schema to be specific to the scanner software version",
    )
    p.add_argument("--participant-label", nargs="+", default=bids.layout.Query.ANY)
    p.add_argument("--session-label", nargs="*", default=[bids.layout.Query.NONE, bids.layout.Query.ANY])
    return p.parse_args()


def main() -> None:
    """Main entry point for the forBIDS CLI.

    Parses arguments and executes either the init or validate command.
    Exits with code 0 on success, 1 on failure.

    Examples:
        >>> # Initialize schemas:
        >>> # forbids init /data/my_bids_dataset
        >>>
        >>> # Validate a subject:
        >>> # forbids validate /data/my_bids_dataset --participant-label 01
    """
    args = parse_args()
    layout = bids.BIDSLayout(os.path.abspath(args.bids_path))
    success = False

    if args.command == "init":
        success = initialize(
            layout,
            uniform_sessions=not args.session_specific,
            uniform_instruments=not args.scanner_specific,
            version_specific=args.version_specific,
        )
    elif args.command == "validate":
        success = process_validation(layout, subject=args.participant_label, session=args.session_label)
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
