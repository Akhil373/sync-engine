
# Office Online

Linux utility for editing local Office files through the OneDrive web editor.

**Stack:** Python, PySide6, SQLite, rclone, OneDrive

```text
Local file
    │
    ▼
rclone copyto
    │
    ▼
OneDrive ──────► OneDrive web editor
    │                    │
    │     poll hashes    │
    ◄────────────────────┘
    │
    ▼
Local file
```

## Sync

| Local     | Remote    | Action                     |
| --------- | --------- | -------------------------- |
| unchanged | unchanged | —                          |
| changed   | unchanged | keep local                 |
| unchanged | changed   | pull remote → local        |
| changed   | changed   | save remote as `.conflict` |

Changes are detected using **QuickXorHash** every 5s. Remote changes must remain stable across two polls before being applied.

Session state and hash baselines are stored in SQLite:

```text
~/.local/state/office-online/office-online.db
```

## Requirements

- Python 3.13+
- `uv`
- `rclone`
- OneDrive remote configured as `onedrive:`
- Linux desktop with `xdg-open`

For auth, this uses **rclone's OneDrive backend instead of dealing with Microsoft Azure app registration, MSAL, client IDs/secrets, redirect URIs, permissions, and all that tedious setup**.

```text
src/office_online/
├── manager.py     # session lifecycle
├── session.py     # hashing, polling, sync/conflicts
├── state.py       # SQLite state
├── rclone.py      # rclone interface
├── gui.py         # PySide6 GUI
├── auth.py        # OneDrive/rclone setup
└── cli.py         # CLI entry point
```
