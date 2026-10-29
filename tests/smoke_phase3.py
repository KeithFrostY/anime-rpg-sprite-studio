"""Real Qt event loop: load/generate, timed preview, apply, save and reopen."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from anime_rpg_sprite_studio.core.project_service import ProjectService
from anime_rpg_sprite_studio.ui.template_dialog import TemplateDialog


def run():
    app = QApplication([])
    with TemporaryDirectory() as root:
        service = ProjectService()
        c = service.add_character()
        service.save(Path(root) / "project.json")
        dialog = TemplateDialog(service, c.id)
        dialog.show()
        dialog.load_demo()
        state = {"stage": "loading", "ticks": 0, "seen": set(), "passed": False}
        timer = QTimer()
        original_question = QMessageBox.question
        def check():
            state["ticks"] += 1
            if state["ticks"] > 500:
                dialog.reject()
                app.exit(1)
                return
            if state["stage"] == "loading" and dialog.generate_button.isEnabled():
                state["stage"] = "generating"
                dialog.generate()
            elif state["stage"] == "generating" and dialog.apply_button.isEnabled():
                assert not c.clips[0].frames and c.template is None
                state["stage"] = "playing"
                dialog.toggle_playback()
            elif state["stage"] == "playing":
                state["seen"].add(dialog.frame_index)
                if len(state["seen"]) == 4:
                    for i in range(4):
                        dialog.direction.setCurrentIndex(i)
                        assert dialog.candidate.frames[list(dialog.candidate.frames)[i]]
                    dialog.direction.setCurrentIndex(0)
                    dialog.grab().save(str(Path(__file__).parents[1] / "docs/phase-3-preview.png"))
                    QMessageBox.question = lambda *a: QMessageBox.StandardButton.Yes
                    dialog.apply_candidate()
                    assert len(c.clips[0].frames) == 16 and c.template is not None
                    service.save(service.path)
                    service.load(service.path)
                    assert not service.repository.missing_assets(service.project, service.path)
                    state["passed"] = True
                    timer.stop()
        timer.timeout.connect(check)
        timer.start(50)
        code = app.exec()
        QMessageBox.question = original_question
        assert state["passed"], "Phase 3 Qt smoke did not finish"
        print("Phase 3: background generation, timed four-frame preview, apply and reopen: PASS")
        return code


if __name__ == "__main__":
    sys.exit(run())
