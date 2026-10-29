"""Explicit offline frozen-app validation; never called on normal startup."""
from contextlib import AbstractContextManager
from pathlib import Path
import json
import socket
import sys
from tempfile import TemporaryDirectory


class OfflineGuard(AbstractContextManager):
    def __enter__(self):
        from keyring.backends.Windows import WinVaultKeyring
        self.saved = []
        def forbidden(*args, **kwargs):
            raise PermissionError("Offline self-test forbids network and real credentials")
        for owner, names in ((socket.socket, ("connect", "connect_ex", "send", "sendall", "sendto", "sendmsg")),
                             (socket, ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")),
                             (WinVaultKeyring, ("get_password", "set_password", "delete_password"))):
            for name in names:
                if not hasattr(owner, name):
                    continue
                self.saved.append((owner, name, getattr(owner, name)))
                setattr(owner, name, forbidden)
        return self

    def __exit__(self, *args):
        for owner, name, original in reversed(self.saved):
            setattr(owner, name, original)


def run_self_test(app, report_path, screenshot_path=None):
    from PySide6.QtCore import QTimer, QThreadPool
    from PySide6.QtWidgets import QMessageBox
    from .runtime import resource_path
    from .ui.main_window import MainWindow
    from .ui.template_dialog import TemplateDialog
    from .ui.quality_dialog import QualityDialog
    from .ui.export_dialog import ExportDialog
    from .export.service import capture_export
    from .ai.mock_provider import MockProvider
    from .ai.contracts import GenerationRequest
    from .security.credentials import WindowsCredentialManager
    from .billing.manager import SQLiteBudgetManager

    report = {"passed": False, "frozen": bool(getattr(sys, "frozen", False)),
              "checks": [], "network": "blocked", "real_vault": "blocked"}
    destination = Path(report_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with OfflineGuard(), TemporaryDirectory(prefix="SpriteStudio-selftest-") as temporary:
        root = Path(temporary)
        window = MainWindow()
        window.show()
        window.add_character()
        window.service.save(root / "測試專案/project.json")
        report["checks"].append("Qt main window and Unicode project save")
        template = TemplateDialog(window.service, window.active_character().id, window)
        template.show()
        template.start_work("load", resource_path("examples/six-layer-demo/template.json"))
        state = {"stage": "template", "ticks": 0, "seen": set(), "quality": None, "export": None}
        timer = QTimer()

        def stop(success):
            timer.stop()
            report["passed"] = success
            report["stage"] = state["stage"]
            for dialog in (state["export"], state["quality"], template):
                if dialog is not None:
                    dialog.reject()
            window.service.dirty = False
            window.close()
            app.exit(0 if success else 1)

        def check():
            try:
                state["ticks"] += 1
                if state["ticks"] > 1000:
                    stop(False)
                    return
                if state["stage"] == "template" and template.generate_button.isEnabled():
                    report["checks"].append("shipped 24-layer PNG template loaded")
                    state["stage"] = "generate"
                    template.generate()
                elif state["stage"] == "generate" and template.apply_button.isEnabled():
                    assert len(template.candidate.frames) == 4
                    original = QMessageBox.question
                    QMessageBox.question = lambda *a: QMessageBox.StandardButton.Yes
                    try:
                        template.apply_candidate()  # Only template apply; no AI confirmation.
                    finally:
                        QMessageBox.question = original
                    window.service.save(window.service.path)
                    window.service.load(window.service.path)
                    window.refresh()
                    report["checks"].append("CPU generation, 16-frame apply, save and reopen")
                    state["stage"] = "preview"
                elif state["stage"] == "preview" and window.play_button.isEnabled():
                    window.onion_check.setChecked(True)
                    window.toggle_playback()
                    state["stage"] = "play"
                elif state["stage"] == "play":
                    state["seen"].add(window.frame_index)
                    if len(state["seen"]) == 4:
                        window.stop_playback()
                        report["checks"].append("timed four-frame playback, onion skin and baseline")
                        snapshot = capture_export(window.active_character(), window.service.path)
                        state["quality"] = QualityDialog(snapshot=snapshot, parent=window)
                        state["quality"].show()
                        state["stage"] = "quality"
                elif state["stage"] == "quality" and not state["quality"].busy:
                    assert len(state["quality"].report.frames) == 16
                    report["checks"].append("background 16-frame quality analysis")
                    state["quality"].reject()
                    snapshot = capture_export(window.active_character(), window.service.path)
                    state["export"] = ExportDialog(snapshot, window)
                    state["export"].show()
                    state["stage"] = "prepare_export"
                elif state["stage"] == "prepare_export" and state["export"].export_button.isEnabled():
                    state["export"].start_export()
                    state["stage"] = "export"
                elif state["stage"] == "export" and not state["export"].busy:
                    output = state["export"].result_path
                    assert output is not None and len([p for p in output.rglob("*") if p.is_file()]) == 18
                    metadata = json.loads((output / "animation.json").read_text(encoding="utf-8"))
                    assert metadata["sheet"]["width"] == 1024
                    report["checks"].append("PNG/sheet/JSON export and full output validation")
                    state["export"].reject()
                    assert MockProvider().generate(GenerationRequest("offline")).png.startswith(b"\x89PNG")
                    class FakeVault:
                        value = None
                        def get_password(self, *args): return self.value
                        def set_password(self, service, user, value): self.value = value
                        def delete_password(self, *args): self.value = None
                    credentials = WindowsCredentialManager(FakeVault())
                    credentials.set_key("fal", "FAKE-OFFLINE-SELFTEST")
                    assert credentials.has_key("fal")
                    credentials.delete_key("fal")
                    ledger = SQLiteBudgetManager(root / "ledger.sqlite3")
                    assert not ledger.list_requests()
                    from .ai.http import SafeHttp
                    assert SafeHttp is not None
                    report["checks"].append("offline Mock, Windows backend import, fake-vault interface, SQLite and HTTPS module")
                    window.statusBar().showMessage("離線打包驗收通過；未使用真實 Key 或 API。")
                    if screenshot_path:
                        target = Path(screenshot_path).resolve()
                        target.parent.mkdir(parents=True, exist_ok=True)
                        assert window.grab().save(str(target))
                    stop(True)
            except Exception:
                # Generic failure report avoids accidentally serializing exception secrets.
                stop(False)

        timer.timeout.connect(check)
        timer.start(50)
        code = app.exec()
        QThreadPool.globalInstance().waitForDone(10000)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return code if report["passed"] else 1
