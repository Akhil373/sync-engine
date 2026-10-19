import argparse
import signal
from pathlib import Path
from .config import STALE_FILES_EXPIRY
import threading

from . import manager


def main() -> None:
    parser = argparse.ArgumentParser(prog="office-online")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()

    manager.init()

    signal.signal(signal.SIGINT, lambda *_: manager.stop_all())
    signal.signal(signal.SIGTERM, lambda *_: manager.stop_all())

    manager.start_session(args.file)

    threading.Thread(
        target=manager.cleanup_old_files, args=(STALE_FILES_EXPIRY,), daemon=True
    ).start()

    manager.join_all()
