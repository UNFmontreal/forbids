from __future__ import annotations

import argparse
import logging
import os

import bids

from .init import initialize
from .validation import validate

DEBUG = bool(os.environ.get("DEBUG", False))
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


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

    if args.command == "init":
        initialize(
            layout,
            uniform_sessions=not args.varying_sessions,
            uniform_instruments=not args.scanner_specific,
            version_specific=args.version_specific
        )
    elif args.command == "validate":
        no_error = True
        for error in validate(layout, subject=args.participant_label, session=args.session_label):
            no_error = False
            print(
                f"{f"{error.__class__}" + '.'.join(error.absolute_path)} : {error.message} found {error.instance if 'required' not in error.message else ''}"
            )
        exit(0 if no_error else 1)


if __name__ == "__main__":
    main()
