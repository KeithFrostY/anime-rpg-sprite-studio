from io import BytesIO

import pytest
from PIL import Image


def png(image):
    stream = BytesIO(); image.save(stream, format='PNG'); return stream.getvalue()


def test_mask_polygon_paint_and_undo_are_nondestructive():
    from anime_rpg_sprite_studio.rendering.mask_paint import PaintDocument
    source = Image.new('RGBA', (12, 12), (200, 50, 10, 128))
    d = PaintDocument(png(source), mask_bytes=png(Image.new('L', source.size, 0)))
    d.polygon([(1,1),(8,1),(8,8),(1,8)], add=True)
    assert d.composite().getpixel((3,3)) == (200,50,10,128)
    assert d.composite().getpixel((10,10))[3] == 0
    d.stroke('mask_erase', [(3,3)], size=3)
    assert d.composite().getpixel((3,3))[3] == 0
    d.undo(); assert d.composite().getpixel((3,3))[3] == 128
    d.redo(); assert d.composite().getpixel((3,3))[3] == 0
    d.stroke('paint', [(10,10)], size=1, color=(0,0,255,128))
    assert d.composite().getpixel((10,10)) == (0,0,255,128)
    assert Image.open(BytesIO(d.result_bytes()[0])).getpixel((3,3)) == (200,50,10,128)


def test_clone_and_transparent_picker():
    from anime_rpg_sprite_studio.rendering.mask_paint import PaintDocument
    image = Image.new('RGBA', (8,8)); image.putpixel((1,1), (20,30,40,255))
    d = PaintDocument(png(image))
    assert d.pick((0,0)) is None
    d.clone((1,1), [(5,5)], size=1)
    assert d.composite().getpixel((5,5)) == (20,30,40,255)
    d.undo(); assert d.composite().getpixel((5,5))[3] == 0


def test_reopen_and_reject_bad_inputs():
    from anime_rpg_sprite_studio.rendering.mask_paint import PaintDocument
    source = png(Image.new('RGBA', (8,8), (20,40,60,100)))
    d = PaintDocument(source); d.stroke('paint', [(6,6)], size=1, color=(255,0,0,255))
    src, mask, paint, composite = d.result_bytes()
    reopened = PaintDocument(src, mask, paint)
    assert reopened.composite().tobytes() == Image.open(BytesIO(composite)).convert('RGBA').tobytes()
    with pytest.raises(ValueError): PaintDocument(source, png(Image.new('L', (3,3))), paint)


def test_dialog_accept_and_cancel_preserve_source(qtbot):
    from anime_rpg_sprite_studio.ui.mask_paint_dialog import MaskPaintDialog
    source = png(Image.new('RGBA', (20,20), (40,80,120,200)))
    dialog = MaskPaintDialog(source); qtbot.addWidget(dialog)
    dialog.document.stroke('paint', [(10,10)], size=3, color=(255,0,0,255))
    dialog.accept()
    assert dialog.result_bytes[0] == source
    assert Image.open(BytesIO(dialog.result_bytes[3])).getpixel((10,10)) == (255,0,0,255)
    other = MaskPaintDialog(source); qtbot.addWidget(other); other.reject()
    assert other.result_bytes is None


def test_canvas_polygon_brush_zoom_and_discard(qtbot, monkeypatch):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    from anime_rpg_sprite_studio.ui.mask_paint_dialog import MaskPaintDialog
    source = png(Image.new('RGBA', (40,40), (80,100,120,255)))
    dialog = MaskPaintDialog(source, png(Image.new('L', (40,40), 0)))
    qtbot.addWidget(dialog); dialog.show(); qtbot.waitExposed(dialog)
    canvas = dialog.canvas
    for pos in (QPoint(5,5), QPoint(25,5), QPoint(25,25), QPoint(5,25)):
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    dialog.finish_polygon()
    assert dialog.document.mask.getpixel((10,10)) == 255
    dialog.tool.setCurrentIndex(dialog.tool.findData('mask_erase'))
    dialog.brush_size.setValue(3)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(10,10))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(20,10))
    assert dialog.document.mask.getpixel((15,10)) == 0
    dialog.undo(); assert dialog.document.mask.getpixel((15,10)) == 255
    dialog.zoom.setValue(200); assert canvas.size().width() == 80
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    dialog.close(); assert dialog.isVisible()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.close(); assert not dialog.isVisible() and dialog.result_bytes is None


def test_reference_size_validation_and_clone_alpha(qtbot):
    from anime_rpg_sprite_studio.rendering.mask_paint import PaintDocument
    from anime_rpg_sprite_studio.ui.mask_paint_dialog import MaskPaintDialog
    source = png(Image.new('RGBA', (10,10), (20,30,40,255)))
    with pytest.raises(ValueError): MaskPaintDialog(source, references=[png(Image.new('RGBA', (2,2)))])
    d = PaintDocument(source, png(Image.new('L', (10,10), 0)))
    d.clone((1,1), [(3,3),(4,3),(5,3)], size=3, opacity=128, sample_source=True)
    assert d.paint.getpixel((4,3))[3] == 128


def test_semitransparent_mask_and_erasing_preserve_alpha():
    from anime_rpg_sprite_studio.rendering.mask_paint import PaintDocument
    d = PaintDocument(png(Image.new('RGBA', (8,8), (80,100,120,128))), png(Image.new('L', (8,8), 128)))
    assert d.composite().getpixel((2,2))[3] == 64
    d.stroke('paint', [(2,2)], size=1, color=(255,0,0,128))
    assert d.composite().getpixel((2,2))[3] == 160
    d.stroke('paint_erase', [(2,2)], size=1)
    assert d.composite().getpixel((2,2))[3] == 64
