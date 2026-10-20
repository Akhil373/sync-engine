import threading
import time
from pathlib import Path

from . import rclone, state
from .auth import ensure_authenticated
from .config import STALE_FILES_EXPIRY
from .logger_config import get_logger
from .session import get_remote_metadata, open_file

log = get_logger(__name__)


_lock = threading.Lock()
sessions: dict[str, str] = {}  # "thread" -> Thread and "stop" -> Event


def init():
    if not state.get_db_path().exists():
        state.init_db()
    ensure_authenticated()


def _run(file: Path, stop: threading.Event):
    try:
        remote_path = f"onedrive:office-online/{file.name}"
        log.info("Opening %s", file)
        rclone.copy_to_remote(str(file), remote_path)
        log.info("Uploaded %s", file.name)
        open_file(file, remote_path, stop)
    except Exception:
        log.exception("Session failed for %s", file)
    finally:
        with _lock:
            sessions.pop(str(file), None)
        log.info("Session ended: %s", file.name)


def start_session(path: Path):
    file = Path(path).resolve()
    key = str(file)
    with _lock:
        existing = sessions.get(key)
        if existing and existing["thread"].is_alive():
            return existing["stop"]
        stop = threading.Event()
        t = threading.Thread(target=_run, args=(file, stop), name=key)
        sessions[key] = {"thread": t, "stop": stop}
    t.start()
    return stop


def stop_all():
    with _lock:
        for s in sessions.values():
            s["stop"].set()


def join_all(timeout: float | None = None):
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        with _lock:
            threads = [s["thread"] for s in sessions.values()]
        alive = [t for t in threads if t.is_alive()]
        if not alive:
            return
        if deadline is not None and time.monotonic() > deadline:
            return
        alive[0].join(0.5)


def cleanup_old_files(days: int = 14) -> int:
    log.info(f"checking for files older than {STALE_FILES_EXPIRY} in remote...")
    removed = 0
    for row in state.get_stale_files(days):
        key = row["local_path"]
        if key in sessions:
            continue
        try:
            if not Path(key).exists():
                continue
            remote_hash, _ = get_remote_metadata(row["remote_path"])
            if remote_hash is None:
                state.mark_cleaned(key)
            elif remote_hash == row["base_remote_hash"]:
                if key in sessions:
                    continue
                rclone.delete_file(row["remote_path"])
                state.mark_cleaned(key)
                removed += 1
            else:
                log.info("Keeping %s: remote has unsynced changes", row["remote_path"])
        except Exception:
            log.exception("cleanup failed for %s", key)
    if removed:
        log.info("Cleaned %d old remote file(s)", removed)
    return removed
