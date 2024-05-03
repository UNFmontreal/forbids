import argparse
import bids
from .init import initialize
from .validate import validate


def parse_args():

    p = argparse.ArgumentParser(description="forbids - setup and validate protocol compliance")
    p.add_argument("command", help="init or validate")
    p.add_argument("bids_path", help="path to the BIDS dataset")
    p.add_argument(
        "--uniform-session",
        type=bool,
        action="store_true",
        default=True,
        help="all sessions will have the same structure, forces to factor session entity",
    )
    return p.parse_args()


def main() -> None:

    layout = bids.BIDSLayout(bids_path)
    args = parse_args()
    if args.command == "init":
        initialize(layout, session_uniform=args.uniform_session)
