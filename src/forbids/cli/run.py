import os
import argparse
import bids
from .init import initialize
from .validation import validate


def parse_args():

    p = argparse.ArgumentParser(description="forbids - setup and validate protocol compliance")
    p.add_argument("command", help="init or validate")
    p.add_argument("bids_path", help="path to the BIDS dataset")
    p.add_argument(
        "--uniform-session",
        action="store_true",
        default=True,
        help="all sessions will have the same structure, forces to factor session entity",
    )
    p.add_argument("--participant-label", nargs="+")
    p.add_argument("--session-label", nargs="*")
    return p.parse_args()


def main() -> None:

    args = parse_args()
    layout = bids.BIDSLayout(os.path.abspath(args.bids_path))

    if args.command == "init":
        initialize(layout, session_uniform=args.uniform_session)
    elif args.command == "validate":
        no_error = True
        for error in validate(layout, subject=args.participant_label, session=args.session_label):
            no_error = False
            print(error)
        exit(0 if no_error else 1)


if __name__ == "__main__":
    main()
