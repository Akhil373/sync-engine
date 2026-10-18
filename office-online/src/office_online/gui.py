import argparse
import logging
import os
import signal
import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QIcon, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import manager

# from .logging_setup import setup_logging

OFFICE_SUFFIXES = {
    ".doc",
    ".docx",
    ".dotx",
    ".odt",
    ".rtf",
    ".xls",
    ".xlsx",
    ".xltx",
    ".ods",
    ".csv",
    ".ppt",
    ".pptx",
    ".potx",
    ".odp",
}
MAX_LINES = 1000
SERVER_NAME = f"office-online-gui-{os.getuid()}"


class Bus(QObject):
    log = Signal(str, str)


bus = Bus()


class QtHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            bus.log.emit(record.threadName or "", self.format(record))
        except Exception:
            self.handleError(record)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Office Online")
        self.resize(940, 540)
        self.setAcceptDrops(True)

        self.entries: dict[str, dict] = {}
        self.closing = False
        self.was_running: set[str] = set()
        self.tray: QSystemTrayIcon | None = None

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _: self._toggle_selected())

        hint = QLabel("Drop files here")
        hint.setAlignment(Qt.AlignCenter)
        hint.setMinimumHeight(72)
        hint.setStyleSheet(
            "border: 2px dashed palette(mid); border-radius: 6px; color: palette(mid);"
        )

        open_btn = QPushButton("Open file…")
        open_btn.clicked.connect(self._pick_files)
        self.action_btn = QPushButton("Stop sync")
        self.action_btn.setEnabled(False)
        self.action_btn.clicked.connect(self._toggle_selected)

        buttons = QHBoxLayout()
        buttons.addWidget(open_btn)
        buttons.addWidget(self.action_btn)

        left = QWidget()
        lay = QVBoxLayout(left)
        lay.addWidget(QLabel("Files"))
        lay.addWidget(self.list, 1)
        lay.addWidget(hint)
        lay.addLayout(buttons)

        self.header = QLabel("Open or drop a file to start")
        f = self.header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self.header.setFont(f)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(MAX_LINES)
        self.view.setFont(QFont("monospace"))
        self.view.setLineWrapMode(QPlainTextEdit.WidgetWidth)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.addWidget(self.header)
        rlay.addWidget(self.view, 1)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)

        bus.log.connect(self._on_log)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(250)

    def setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = QIcon.fromTheme(
            "office-online",
            self.style().standardIcon(QStyle.SP_FileIcon),
        )
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Office Online")

        menu = QMenu(self)
        show = QAction("Show window", self)
        show.triggered.connect(self.show_window)
        quit_ = QAction("Quit", self)
        quit_.triggered.connect(self.request_quit)
        menu.addAction(show)
        menu.addSeparator()
        menu.addAction(quit_)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()

    def _on_tray_click(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def notify(self, title: str, body: str = "") -> None:
        if self.tray is not None:
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 5000)

    def add_files(self, paths) -> None:
        for p in paths:
            path = Path(p).expanduser().resolve()
            if not path.is_file():
                self.statusBar().showMessage(f"Not a file: {path.name}", 5000)
                continue
            if path.suffix.lower() not in OFFICE_SUFFIXES:
                self.statusBar().showMessage(
                    f"Skipped {path.name}: not an Office file", 5000
                )
                continue
            self._add_one(path)

    def _add_one(self, path: Path) -> None:
        key = str(path)
        if key not in self.entries:
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, key)
            item.setToolTip(key)
            self.entries[key] = {
                "item": item,
                "lines": deque(maxlen=MAX_LINES),
                "name": path.name,
            }
            self.list.addItem(item)
        manager.start_session(path)
        self.list.setCurrentItem(self.entries[key]["item"])
        self._refresh()

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Open Office files")
        self.add_files(files)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        self.add_files(u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile())

    def _current_key(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_select(self, *_) -> None:
        key = self._current_key()
        self.view.clear()
        if key is None:
            self.header.setText("Open or drop a file to start")
            self.action_btn.setEnabled(False)
            return
        self.view.setPlainText("\n".join(self.entries[key]["lines"]))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        self._refresh()

    def _on_log(self, key: str, line: str) -> None:
        entry = self.entries.get(key)
        if entry is None:
            return
        entry["lines"].append(line)
        if key == self._current_key():
            self.view.appendPlainText(line)

    def _refresh(self) -> None:
        running = set(manager.sessions)
        dim = self.palette().color(QPalette.Disabled, QPalette.Text)
        normal = self.palette().color(QPalette.Active, QPalette.Text)
        for key, e in self.entries.items():
            is_running = key in running
            e["item"].setText(e["name"] if is_running else f"{e['name']}  (ended)")
            e["item"].setForeground(normal if is_running else dim)

        key = self._current_key()
        if key is not None:
            is_running = key in running
            state = "syncing" if is_running else "ended"
            self.header.setText(f"{self.entries[key]['name']}  ·  {state}")
            self.action_btn.setText("Stop sync" if is_running else "Reopen")
            self.action_btn.setEnabled(not self.closing)

        if not self.closing:
            for key in self.was_running - running:
                self.notify("Sync finished", self.entries[key]["name"])
        self.was_running = running

        if self.closing and not running:
            QApplication.quit()

    def _toggle_selected(self) -> None:
        key = self._current_key()
        if key is None or self.closing:
            return
        if key in manager.sessions:
            manager.sessions[key]["stop"].set()  # final pull runs, then it ends
            self.entries[key]["lines"].append("Stopping… finishing sync")
            self.view.appendPlainText("Stopping… finishing sync")
        else:
            manager.start_session(Path(key))

    def request_quit(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.action_btn.setEnabled(False)
        if not manager.sessions:
            QApplication.quit()
            return
        self.statusBar().showMessage("Finishing sync before quitting…")
        self.notify("Finishing sync", "Office Online will quit when it is done")
        manager.stop_all()

    def closeEvent(self, e) -> None:
        if self.closing:
            e.ignore()
            return
        if self.tray is not None:
            e.ignore()
            self.hide()
            if manager.sessions:
                self.notify("Still syncing", "Office Online is running in the tray")
            return
        if not manager.sessions:
            e.accept()
            return
        e.ignore()
        self.request_quit()


def send_to_running_instance(paths: list[Path]) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(300):
        return False
    lines = ["SHOW"] + [str(p.expanduser().resolve()) for p in paths]
    sock.write(("\n".join(lines) + "\n").encode())
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def start_server(window: "MainWindow") -> QLocalServer:
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer(window)
    if not server.listen(SERVER_NAME):
        logging.getLogger(__name__).warning(
            "single-instance socket: %s", server.errorString()
        )

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        buf = bytearray()

        def read() -> None:
            buf.extend(conn.readAll().data())
            *lines, rest = buf.decode().split("\n")
            del buf[:]
            buf.extend(rest.encode())
            paths = []
            for line in lines:
                if line == "SHOW":
                    window.show_window()
                elif line:
                    paths.append(line)
            if paths:
                window.add_files(paths)

        conn.readyRead.connect(read)
        conn.disconnected.connect(conn.deleteLater)
        read()

    server.newConnection.connect(on_connection)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(prog="office-online-gui")
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setDesktopFileName("office-online")

    if send_to_running_instance(args.files):
        return

    # setup_logging()
    manager.init()

    window = MainWindow()
    window.setup_tray()
    server = start_server(window)

    handler = QtHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)

    signal.signal(signal.SIGINT, lambda *_: window.request_quit())
    signal.signal(signal.SIGTERM, lambda *_: window.request_quit())

    window.show()
    window.add_files(args.files)
    sys.exit(app.exec())
