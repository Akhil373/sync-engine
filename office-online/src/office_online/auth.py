from . import rclone


def ensure_authenticated() -> None:
    if not rclone.is_installed():
        raise RuntimeError(
            "rclone is not installed. Install it with your package manager."
        )

    if rclone.is_auth():
        return

    print("OneDrive is not authenticated.")
    print("Starting rclone configuration...\n")

    rclone.configure()

    if not rclone.is_auth():
        raise RuntimeError("OneDrive authentication failed.")
