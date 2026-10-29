"""Real Qt prepare/export workflow; optional persistent diagnostic export example."""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import sys
import json

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from anime_rpg_sprite_studio.animation.templates import demo_template
from anime_rpg_sprite_studio.animation.walk import generate_walk
from anime_rpg_sprite_studio.core.project_service import ProjectService
from anime_rpg_sprite_studio.export.service import capture_export
from anime_rpg_sprite_studio.ui.export_dialog import ExportDialog


def run():
    app = QApplication([])
    workspace = Path(__file__).parents[1]
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        service = ProjectService()
        character = service.add_character()
        character.name = "六層測試人偶 · Walk"
        service.save(root / "project.json")
        template, assets = demo_template()
        walk = generate_walk(template, assets)
        service.apply_walk(character.id, template, assets, walk.frames)
        snapshot = capture_export(character, service.path)
        dialog = ExportDialog(snapshot)
        if "--keep-example" in sys.argv:
            output_parent = workspace / "examples/export-demo"
            output_parent.mkdir(parents=True, exist_ok=True)
            dialog.folder_edit.setText(str(output_parent))
        dialog.show()
        state = {"stage": "prepare", "ticks": 0, "passed": False}
        timer = QTimer()
        def check():
            state["ticks"] += 1
            if state["ticks"] > 400:
                dialog.reject()
                app.exit(1)
                return
            if state["stage"] == "prepare" and dialog.export_button.isEnabled():
                state["stage"] = "export"
                dialog.start_export()
            elif state["stage"] == "export" and not dialog.busy:
                result = dialog.result_path
                assert result is not None, dialog.status.text()
                assert len([p for p in result.rglob("*") if p.is_file()]) == 18
                metadata = json.loads((result / "animation.json").read_text(encoding="utf-8"))
                assert metadata["animation"]["fps"] == 8
                with Image.open(result / "walk_sheet.png") as sheet:
                    assert sheet.mode == "RGBA" and sheet.size == (1024, 1024)
                shutil.copyfile(result / "walk_sheet.png", workspace / "docs/phase-4-sheet.png")
                dialog.grab().save(str(workspace / "docs/phase-4-preview.png"))
                assert service.dirty  # Export did not save or edit the source project.
                state["passed"] = True
                timer.stop()
                print("Qt prepare/progress/export: PASS")
                print("Exported:", result)
                dialog.reject()
        timer.timeout.connect(check)
        timer.start(50)
        code = app.exec()
        assert state["passed"], "Phase 4 smoke incomplete"
        return code


if __name__ == "__main__":
    sys.exit(run())
