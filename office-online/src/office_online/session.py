from pathlib import Path
import json
import time
from . import rclone, state
import subprocess

POLL_INTERVAL = 15


def get_remote_metadata(remote_path: str) -> tuple[str, str]:
    result = rclone.run(
        "lsjson",
        "--stat",
        "--hash",
        remote_path,
    )

    data = json.loads(result.stdout)

    remote_hash = data["Hashes"]["quickxor"]
    remote_id = data["ID"]

    return remote_hash, remote_id


def open_file(local_path: Path, remote_path: str):
    local_hash = rclone.run("hashsum", "quickxor", local_path).stdout.split()[0]
    remote_hash, remote_id = get_remote_metadata(remote_path)

    print("local hash:", local_hash)
    print("remote id and hash:", remote_id, remote_hash)

    state.create_session(
        local_path=local_path,
        remote_path=remote_path,
        remote_item_id=remote_id,
        base_local_hash=local_hash,
        base_remote_hash=remote_hash,
    )

    url = rclone.get_edit_url(remote_path)

    print("fetched url:", url[:10])

    subprocess.Popen(["xdg-open", url])

    poll_session(local_path)


def poll_session(local_path: Path, remote_path: str) -> None:
    while True:
        session = state.get_session(str(local_path))

        if session is None:
            return

        if session["state"] != "active":
            return

        # local_hash = rclone.run("hashsum", "quickxor", local_path).stdout.split()[0]
        # remote_hash, remote_id = get_remote_metadata(remote_path)
        #
        # base_local_hash, base_remomte_hash = (
        #     session["base_local_hash"],
        #     session["base_remote_hash"],
        # )

        # TODO:
        # 1. Get current local SHA-256
        # 2. Get current remote QuickXorHash
        # 3. Compare against baseline
        # 4. Sync / conflict handling

        time.sleep(POLL_INTERVAL)
