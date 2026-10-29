from io import BytesIO
import pytest
from PIL import Image, ImageDraw


def frames():
    from anime_rpg_sprite_studio.core.models import Direction
    result = {}
    for direction in Direction:
        result[direction] = {}
        for i in range(4):
            image = Image.new("RGBA", (256, 256))
            ImageDraw.Draw(image).rectangle((90, 30, 166, 244), fill="blue")
            stream = BytesIO()
            image.save(stream, format="PNG")
            result[direction][i] = stream.getvalue()
    return result


def test_quality_stable_frames_no_jitter():
    from anime_rpg_sprite_studio.animation.quality import analyze_frames
    report = analyze_frames(frames())
    assert len(report.frames) == 16
    assert not report.warnings
    assert report.frames[0].bounds == (90, 30, 167, 245)


def test_quality_flags_empty_opaque_clipped_and_jitter():
    from anime_rpg_sprite_studio.animation.quality import analyze_frames
    from anime_rpg_sprite_studio.core.models import Direction
    data = frames()
    images = [Image.new("RGBA", (256, 256)), Image.new("RGBA", (256, 256), "blue")]
    shifted = Image.new("RGBA", (256, 256))
    ImageDraw.Draw(shifted).rectangle((120, 40, 196, 220), fill="blue")
    images.append(shifted)
    for i, image in enumerate(images):
        stream = BytesIO()
        image.save(stream, format="PNG")
        data[Direction.FRONT][i] = stream.getvalue()
    report = analyze_frames(data)
    codes = {warning.code for warning in report.warnings}
    assert {"empty", "opaque", "edge", "foot", "jitter", "size"}.issubset(codes)


def test_quality_cancel_and_missing_frames():
    from threading import Event
    from anime_rpg_sprite_studio.animation.quality import analyze_frames
    data = frames()
    cancel = Event()
    cancel.set()
    with pytest.raises(ValueError):
        analyze_frames(data, cancel)
    next(iter(data.values())).pop(3)
    with pytest.raises(ValueError):
        analyze_frames(data)


def test_onion_skin_and_baseline_change_display_only(qtbot):
    from PySide6.QtGui import QPixmap
    from anime_rpg_sprite_studio.ui.preview import Preview
    widget = Preview()
    qtbot.addWidget(widget)
    widget.resize(320, 320)
    current = QPixmap(256, 256)
    from PySide6.QtCore import Qt
    current.fill(Qt.GlobalColor.transparent)
    previous = QPixmap(256, 256)
    previous.fill(Qt.GlobalColor.blue)
    original = current.toImage()
    widget.pixmap = current
    widget.set_neighbors(previous, QPixmap())
    widget.set_onion(False)
    widget.set_baseline(False)
    widget.show()
    before = widget.grab().toImage()
    widget.set_onion(True)
    after = widget.grab().toImage()
    assert before.pixelColor(50, 50) != after.pixelColor(50, 50)
    widget.set_baseline(True)
    baseline = widget.grab().toImage()
    assert baseline.pixelColor(45, 287) != after.pixelColor(45, 287)
    assert current.toImage() == original


def test_quality_dialog_background_read_only(qtbot):
    from anime_rpg_sprite_studio.ui.quality_dialog import QualityDialog
    data = frames()
    original = {d: dict(batch) for d, batch in data.items()}
    dialog = QualityDialog(frames=data)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: not dialog.busy, timeout=10000)
    assert dialog.report is not None and dialog.table.rowCount() == 16
    assert data == original
    dialog.reject()


def test_repeated_preview_timers_stop_on_close(qtbot):
    from anime_rpg_sprite_studio.ui.main_window import MainWindow
    for _ in range(5):
        window = MainWindow()
        qtbot.addWidget(window)
        window.playback_timer.start(10)
        window.close()
        assert not window.playback_timer.isActive()


def test_packaged_resource_resolution_and_generic_exception_hook(qtbot, monkeypatch):
    from anime_rpg_sprite_studio.runtime import resource_path, install_exception_handler
    from PySide6.QtWidgets import QMessageBox
    import sys
    assert resource_path("examples/six-layer-demo/template.json").is_file()
    messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args))
    original = sys.excepthook
    install_exception_handler()
    try:
        sys.excepthook(ValueError, ValueError("FAKE-SECRET-DO-NOT-ECHO"), None)
    finally:
        sys.excepthook = original
    assert messages and "FAKE-SECRET" not in str(messages)


def test_packaged_self_test_guard_forbids_network_and_real_vault(monkeypatch):
    from anime_rpg_sprite_studio.selftest import OfflineGuard
    import socket
    from keyring.backends.Windows import WinVaultKeyring
    original = socket.socket.connect
    resolutions, datagrams = [], []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: resolutions.append(args) or [])
    monkeypatch.setattr(socket.socket, "sendto", lambda *args: datagrams.append(args) or 1)
    with OfflineGuard():
        with socket.socket() as connection:
            with pytest.raises(PermissionError):
                connection.connect(("127.0.0.1", 1))
        with pytest.raises(PermissionError):
            WinVaultKeyring().get_password("unused", "unused")
        with pytest.raises(PermissionError):
            socket.getaddrinfo("api.fal.ai", 443)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as datagram:
            with pytest.raises(PermissionError):
                datagram.sendto(b"test", ("127.0.0.1", 12345))
    assert not resolutions and not datagrams
    assert socket.socket.connect is original
