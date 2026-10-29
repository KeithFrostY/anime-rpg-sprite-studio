"""Qt offline smoke: fake vault and fake HTTP only; no live request or key."""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from uuid import uuid4
import sys

from PIL import Image, ImageDraw
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from anime_rpg_sprite_studio.ai.session import AISession
from anime_rpg_sprite_studio.security.credentials import WindowsCredentialManager
from anime_rpg_sprite_studio.ui.ai_dialog import AIDialog


class FakeVault:
    def get_password(self, *args):
        return "FAKE-SMOKE-KEY"


class FakeHttp:
    def __init__(self):
        self.remote = str(uuid4())
        self.submissions = 0
    def json(self, method, url, *, key, payload=None):
        if "/pricing?" in url:
            return {"prices": [{"endpoint_id": "fal-ai/flux/schnell", "unit_price": Decimal("0.012"), "unit": "image", "currency": "USD"}]}
        if "billing-events?" in url:
            return {"billing_events": [{"request_id": self.remote, "endpoint_id": "fal-ai/flux/schnell",
                    "timestamp": datetime.now(timezone.utc).isoformat(), "cost_total": Decimal("0.010")}], "has_more": False, "next_cursor": None}
        if method == "POST":
            self.submissions += 1
            return {"request_id": self.remote}
        if url.endswith("/status"):
            return {"status": "COMPLETED"}
        return {"images": [{"url": "https://v3.fal.media/fake.png"}]}
    def request(self, method, url, *, key=None, **kwargs):
        assert key is None
        image = Image.new("RGBA", (256, 256))
        draw = ImageDraw.Draw(image)
        draw.ellipse((94, 25, 162, 93), fill="#e8b790")
        draw.rectangle((88, 94, 168, 190), fill="#637bd6")
        draw.rectangle((96, 190, 120, 250), fill="#454555")
        draw.rectangle((136, 190, 160, 250), fill="#454555")
        draw.text((8, 8), "OFFLINE FAKE", fill="#666666")
        out = BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()


def run():
    def forbidden(*args, **kwargs):
        raise AssertionError("Smoke must not use network")
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    app = QApplication([])
    with TemporaryDirectory() as temporary:
        http = FakeHttp()
        session = AISession(temporary, credentials=WindowsCredentialManager(FakeVault()), http=http)
        dialog = AIDialog(session)
        dialog.show()
        dialog.provider.setCurrentIndex(1)
        dialog.prompt.setPlainText("OFFLINE TEST: anime RPG hero")
        dialog.get_quote()
        state = {"stage": "quote", "ticks": 0, "passed": False}
        timer = QTimer()
        original = QMessageBox.question
        QMessageBox.question = lambda *args: QMessageBox.StandardButton.Yes
        def check():
            state["ticks"] += 1
            if state["ticks"] > 300:
                app.exit(1)
                return
            if dialog.busy:
                return
            if state["stage"] == "quote":
                assert dialog.quote is not None
                state["stage"] = "submit"
                dialog.submit_paid()
            elif state["stage"] == "submit":
                assert http.submissions == 1
                state["stage"] = "status"
                dialog.history.setCurrentCell(0, 0)
                dialog.recover("status")
            elif state["stage"] == "status":
                state["stage"] = "result"
                dialog.history.setCurrentCell(0, 0)
                dialog.recover("result")
            elif state["stage"] == "result":
                assert dialog.candidate is not None
                state["stage"] = "billing"
                dialog.history.setCurrentCell(0, 0)
                dialog.recover("billing")
            else:
                row = session.budget.list_requests()[0]
                assert row["actual"] == "0.010" and not row["billing_unresolved"]
                assert http.submissions == 1
                dialog.status.setText("離線驗收：假 Key／假 HTTP，沒有真實 API 請求或費用。")
                dialog.candidate_label.setText("測試替身圖片，不是真實 fal.ai 成果")
                dialog.grab().save(str(Path(__file__).parents[1] / "docs/phase-5-preview.png"))
                timer.stop()
                state["passed"] = True
                dialog.reject()
        timer.timeout.connect(check)
        timer.start(50)
        code = app.exec()
        QMessageBox.question = original
        assert state["passed"]
        print("Offline Qt: quote, explicit confirmation, single fake submit, status, candidate, billing: PASS")
        return code


if __name__ == "__main__":
    sys.exit(run())
