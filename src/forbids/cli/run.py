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
    logging.basicConfig(
        format="%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s", level=logging.INFO
    )
    logging.root.setLevel(logging.INFO)

lgr = logging.getLogger(__name__)


def parse_args():

    p = argparse.ArgumentParser(description="forbids - setup and validate protocol compliance")
    p.add_argument("command", help="init or validate")
    p.add_argument("bids_path", help="path to the BIDS dataset")
    p.add_argument(
        "--varying-sessions",
        action="store_true",
        default=False,
        help="all sessions will have the same structure, forces to factor session entity",
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
    args = parse_args()
    layout = bids.BIDSLayout(os.path.abspath(args.bids_path))
    success = False

    if args.command == "init":
        success = initialize(
            layout,
            uniform_sessions=not args.varying_sessions,
            uniform_instruments=not args.scanner_specific,
            version_specific=args.version_specific,
        )
    elif args.command == "validate":
        success = process_validation(layout, subject=args.participant_label, session=args.session_label)
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
