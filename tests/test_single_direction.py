import json
from PIL import Image
import pytest

from anime_rpg_sprite_studio.animation.single_direction import split_grid, export_animation


def test_manual_boxes_normalize_and_adjust_without_losing_pixels():
    from anime_rpg_sprite_studio.animation.single_direction import crop_boxes, normalize_frames
    image = Image.new('RGBA', (10, 8), (8, 9, 10, 77))
    frames = crop_boxes(image, [(0, 0, 4, 4), (2, 1, 8, 7)])
    normalized = normalize_frames(frames, [(0, 0), (0, 0)])
    assert [frame.size for frame in normalized] == [(6, 6), (6, 6)]
    assert normalized[0].getpixel((1, 2)) == (8, 9, 10, 77)
    assert normalized[0].getpixel((0, 0))[3] == 0
    shifted = normalize_frames(frames, [(1, -1), (0, 0)])
    assert shifted[0].getpixel((2, 1)) == (8, 9, 10, 77)
    with pytest.raises(ValueError):
        crop_boxes(image, [(0, 0, 11, 4)])


def test_split_and_export_preserve_pixels_and_order(tmp_path):
    image = Image.new('RGBA', (6, 4))
    colors = [(i * 30, 12, 24, 255) for i in range(6)]
    for i, color in enumerate(colors):
        image.paste(color, ((i % 3) * 2, (i // 3) * 2, (i % 3 + 1) * 2, (i // 3 + 1) * 2))
    frames = split_grid(image, 3, 2)
    assert [f.getpixel((0, 0)) for f in frames] == colors
    folder = export_animation(frames[::-1], tmp_path, 'attack', 'right', 8, False)
    data = json.loads((folder / 'animation.json').read_text(encoding='utf-8'))
    assert data['loop'] is False and data['direction'] == 'right'
    assert len(data['frames']) == 6
    sheet = Image.open(folder / 'sheet.png')
    assert sheet.size == (12, 2)
    assert sheet.getpixel((0, 0)) == colors[-1]


def test_split_rejects_uneven_grid():
    with pytest.raises(ValueError):
        split_grid(Image.new('RGB', (7, 4)), 3, 2)


def test_crop_region_limits_grid_and_rejects_invalid_bounds():
    image = Image.new('RGBA', (10, 8), 'red')
    image.paste('blue', (2, 2, 8, 6))
    frames = split_grid(image, 3, 2, (2, 2, 8, 6))
    assert len(frames) == 6 and all(f.size == (2, 2) and f.getpixel((0, 0)) == (0, 0, 255, 255) for f in frames)
    with pytest.raises(ValueError):
        split_grid(image, 3, 2, (-1, 2, 8, 6))


def test_failed_export_leaves_no_output(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(Image.Image, 'save', fail)
    with pytest.raises(OSError):
        export_animation([Image.new('RGBA', (2, 2))], tmp_path, 'walk', 'right', 8, True)
    assert list(tmp_path.iterdir()) == []


def test_dialog_load_reorder_and_play(qtbot, tmp_path):
    from anime_rpg_sprite_studio.ui.single_direction_dialog import SingleDirectionDialog
    image = Image.new('RGB', (6, 4), 'red')
    image.paste('blue', (2, 0, 4, 2))
    path = tmp_path / 'grid.png'
    image.save(path)
    dialog = SingleDirectionDialog()
    qtbot.addWidget(dialog)
    dialog.load_image(path)
    assert len(dialog.frames) == 6
    dialog.listing.setCurrentRow(0)
    dialog.move_frame(1)
    assert dialog.frames[0].getpixel((0, 0))[:3] == (0, 0, 255)
    dialog.kind.setCurrentIndex(1)
    assert not dialog.loop.isChecked()
    dialog.margins[0].setValue(3)
    dialog.resplit()
    assert len(dialog.frames) == 6 and dialog.frames[0].size == (1, 2)
    dialog.close()


def test_manual_editor_draw_overlap_reorder_and_move(qtbot, tmp_path):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from anime_rpg_sprite_studio.ui.single_direction_dialog import SingleDirectionDialog
    path = tmp_path / 'image.png'
    Image.new('RGBA', (120, 120), 'red').save(path)
    dialog = SingleDirectionDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.load_image(path)
    dialog.mode.setCurrentIndex(1)
    qtbot.waitExposed(dialog)
    editor = dialog.crop_editor
    rect = editor.geometry_for_image()
    def point(x, y):
        return QPoint(round(rect.x() + x * rect.width() / 120), round(rect.y() + y * rect.height() / 120))
    def drag(a, b):
        QTest.mousePress(editor, Qt.MouseButton.LeftButton, pos=point(*a))
        QTest.mouseRelease(editor, Qt.MouseButton.LeftButton, pos=point(*b))
    drag((10, 10), (60, 60))
    editor.draw_new = True
    drag((30, 30), (100, 100))
    assert len(dialog.frames) == 2
    assert dialog.frames[0].size == (50, 50)
    assert dialog.frames[1].size == (70, 70)
    dialog.listing.setCurrentRow(0)
    dialog.offset_x.setValue(5)
    assert dialog.normalized()[0].size == (70, 70)
    dialog.move_frame(1)
    assert dialog.offsets == [(0, 0), (5, 0)]
    assert dialog.crop_editor.boxes[1] == (10, 10, 60, 60)
    drag((20, 20), (25, 25))
    assert dialog.crop_editor.boxes[1] == (15, 15, 65, 65)
    drag((65, 65), (75, 80))
    assert dialog.crop_editor.boxes[1] == (15, 15, 75, 80)
    dialog.delete_box()
    assert len(dialog.frames) == 1
    dialog.close()
