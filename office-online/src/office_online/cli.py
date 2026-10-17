import subprocess
import argparse
from pathlib import Path
import os

from .auth import ensure_authenticated
from .session import open_file
from . import rclone
from . import state


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="office-online",
    )

    if not state.get_db_path().exists():
        state.init_db()

    parser.add_argument("file", type=Path)

    args = parser.parse_args()

    ensure_authenticated()

    print(f"Opening {args.file}")

    file = Path(args.file).resolve()

    ensure_authenticated()

    remote_path = f"onedrive:office-online/{file.name}"

    rclone.copy_to_remote(
        str(file),
        remote_path,
    )

    print(f"Uploaded {file.name}")

    open_file(file, remote_path)
