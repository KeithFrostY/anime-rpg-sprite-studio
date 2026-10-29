"""Bounded Windows Qt smoke test, using generated diagnostic fixtures only."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
from PIL import Image, ImageDraw
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from anime_rpg_sprite_studio.core.models import Direction
from anime_rpg_sprite_studio.ui.main_window import MainWindow


def run():
    app = QApplication([])
    with TemporaryDirectory() as root:
        w = MainWindow()
        w.add_character()
        w.service.save(Path(root) / "project.json")
        for d in Direction:
            images = {}
            for i in range(4):
                image = Image.new("RGBA", (256, 256))
                draw = ImageDraw.Draw(image)
                draw.ellipse((96, 30, 160, 94), fill="#e3b28e")
                draw.rectangle((88, 94, 168, 190), fill="#5a77d4")
                offset = [-8, 0, 8, 0][i]
                draw.rectangle((95 + offset, 190, 119 + offset, 255), fill="#404050")
                draw.rectangle((137 - offset, 190, 161 - offset, 255), fill="#404050")
                draw.text((8, 8), f"TEST {d.value} {i}", fill="#333333")
                stream = BytesIO()
                image.save(stream, format="PNG")
                images[i] = stream.getvalue()
            w.service.import_frames(w.active_character().id, d, images)
        w.service.save(w.service.path)
        w.refresh()
        w.show()
        state = {"direction": 0, "ticks": 0, "passed": False}
        timer = QTimer()
        def check():
            state["ticks"] += 1
            if state["ticks"] > 100:
                app.exit(1)
                return
            if not w.play_button.isEnabled():
                return
            w.toggle_playback()
            assert w.playback_timer.isActive()
            for expected in (1, 2, 3, 0):
                w.advance_frame()
                assert w.frame_index == expected
            w.stop_playback()
            state["direction"] += 1
            if state["direction"] < 4:
                w.direction.setCurrentIndex(state["direction"])
                assert w.frame_index == 0
            else:
                w.grab().save(str(Path(__file__).parents[1] / "docs/phase-2-preview.png"))
                state["passed"] = True
                timer.stop()
                w.service.dirty = False
                w.close()
        timer.timeout.connect(check)
        timer.start(50)
        code = app.exec()
        assert state["passed"], "Four-direction smoke incomplete"
        print("Four directions, 16 valid frames, playback cycle and screenshot: PASS")
        return code


if __name__ == "__main__":
    sys.exit(run())
