import subprocess
import shutil


def is_installed() -> bool:
    return shutil.which("rclone") is not None


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["rclone", *args], check=True, capture_output=True, text=True)


def is_auth() -> bool:
    try:
        run("lsd", "onedrive:")
        return True
    except subprocess.CalledProcessError:
        return False


def configure() -> None:
    subprocess.run(
        ["rclone", "config"],
        check=True,
    )


def copy_to_remote(local_path: str, remote_path: str) -> None:
    run(
        "copyto",
        local_path,
        remote_path,
    )


def get_edit_url(remote_path: str) -> str:
    result = run(
        "link",
        remote_path,
        "--onedrive-link-type",
        "edit",
    )

    return result.stdout.strip()
