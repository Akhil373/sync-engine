from pathlib import Path
import json
import threading
import os
import signal
import time
from . import rclone, state
import subprocess
from .logger_config import get_logger

POLL_INTERVAL = 5

log = get_logger(__name__)


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


def open_file(local_path: Path, remote_path: str, stop: threading.Event):
    try:
        local_hash = rclone.run("hashsum", "quickxor", local_path).stdout.split()[0]
        remote_hash, remote_id = get_remote_metadata(remote_path)

        log.info("local hash: %s", local_hash)
        log.info("remote hash: %s", remote_hash)
        log.info("remote id: %s", remote_id)

        state.create_session(
            local_path=local_path,
            remote_path=remote_path,
            remote_item_id=remote_id,
            base_local_hash=local_hash,
            base_remote_hash=remote_hash,
        )

        url = rclone.get_edit_url(remote_path)

        log.info("fetched url: %s", url[:15])

        subprocess.Popen(["xdg-open", url])

        poll_session(local_path, remote_path, stop)
    finally:
        log.info("Ensuring clean syncronization...wait")
        time.sleep(4)
        final_pull(local_path, remote_path)


def file_hash(path):
    return rclone.run("hashsum", "quickxor", str(path)).stdout.split()[0]


def poll_session(
    local_path: Path, remote_path: str, stop: threading.Event, idle_timeout=7200
) -> None:
    previous_remote_hash, debounce_count = None, 0
    last_activity = time.monotonic()

    while not stop.is_set():
        session = state.get_session(str(local_path))

        if session is None or time.monotonic() - last_activity > idle_timeout:
            return

        try:
            local_hash = file_hash(local_path)
            remote_hash, _ = get_remote_metadata(remote_path)
        except Exception:
            # time.sleep(POLL_INTERVAL)
            stop.wait(POLL_INTERVAL)
            continue

        base_local_hash, base_remomte_hash = (
            session["base_local_hash"],
            session["base_remote_hash"],
        )

        if remote_hash == base_remomte_hash:
            previous_remote_hash, debounce_count = None, 0
        else:  # remote != base
            log.info("found remote changes")
            if remote_hash == previous_remote_hash:  # remote changed once (== prev)
                debounce_count += 1
            else:  # remote changed multiple times (!= prev)
                previous_remote_hash, debounce_count = remote_hash, 1

            if debounce_count >= 2:  # remote is stable (didnt change in >=2 polls)
                if local_hash != base_local_hash:
                    conflict = local_path.with_name(
                        f"{local_path.stem}.conflict{local_path.suffix}"
                    )
                    rclone.run("copyto", remote_path, str(conflict))
                    state.update_baseline(str(local_path), base_local_hash, remote_hash)

                else:  # remote changed yet local remains same as base
                    log.info("remote changed and is stable, syncing to local")
                    tmp = local_path.with_name(local_path.name + ".tmp")
                    rclone.run("copyto", remote_path, str(tmp))
                    os.replace(tmp, local_path)
                    state.update_baseline(
                        str(local_path), file_hash(local_path), remote_hash
                    )

                previous_remote_hash, debounce_count = None, 0
                last_activity = time.monotonic()
        # time.sleep(POLL_INTERVAL)
        stop.wait(POLL_INTERVAL)


def final_pull(local_path: str, remote_path: str):
    try:
        session = state.get_session(str(local_path))
        if session is None:
            return
        base_remote_hash = session["base_remote_hash"]
        remote_hash, _ = get_remote_metadata(remote_path)

        if remote_hash == base_remote_hash:
            return
        log.info("remote changes found, syncronizing...")
        tmp = local_path.with_name(local_path.name + ".tmp")
        rclone.run("copyto", remote_path, str(tmp))
        os.replace(tmp, local_path)
        state.update_baseline(str(local_path), file_hash(local_path), remote_hash)
    except Exception as e:
        log.info(f"Final sync failed: {e}")
