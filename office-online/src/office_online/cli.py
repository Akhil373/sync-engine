import argparse
import signal
from pathlib import Path

from . import manager


def main() -> None:
    parser = argparse.ArgumentParser(prog="office-online")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()

    manager.init()

    signal.signal(signal.SIGINT, lambda *_: manager.stop_all())
    signal.signal(signal.SIGTERM, lambda *_: manager.stop_all())

    manager.start_session(args.file)
    manager.join_all()
