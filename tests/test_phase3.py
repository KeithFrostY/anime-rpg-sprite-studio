from copy import deepcopy
from io import BytesIO
import json
from threading import Event

import pytest
from PIL import Image


def demo():
    from anime_rpg_sprite_studio.animation.templates import demo_template
    return demo_template()


def test_template_has_four_views_six_layers():
    template, assets = demo()
    template.validate()
    assert len(template.views) == 4 and len(assets) == 24
    assert all(len(view.layers) == 6 for view in template.views)


@pytest.mark.parametrize("change", ["missing", "duplicate", "joint", "escape", "nan", "parameter"])
def test_template_rejects_invalid(change):
    template, assets = demo()
    if change == "missing":
        template.views.pop()
    elif change == "duplicate":
        template.views[0].layers[0].part = template.views[0].layers[1].part
    elif change == "joint":
        template.views[0].layers[0].joint = (256, 100)
    elif change == "escape":
        template.views[0].layers[0].asset_path = "../secret.png"
    elif change == "nan":
        template.parameters.arm_swing = float("nan")
    else:
        template.parameters.bob = 7
    with pytest.raises(ValueError):
        template.validate()


def test_deterministic_walk_and_cancel():
    from anime_rpg_sprite_studio.animation.walk import generate_walk, GenerationCancelled
    template, assets = demo()
    result = generate_walk(template, assets)
    assert result.frames == generate_walk(template, assets).frames
    assert len(result.frames) == 4
    for frames in result.frames.values():
        assert set(frames) == {0, 1, 2, 3}
        assert frames[0] != frames[2]
        for data in frames.values():
            image = Image.open(BytesIO(data))
            assert image.mode == "RGBA" and image.size == (256, 256)
            assert image.getpixel((0, 0))[3] == 0
    stop = Event()
    stop.set()
    with pytest.raises(GenerationCancelled):
        generate_walk(template, assets, stop)


def test_compositing_order_and_clipping_warning():
    from anime_rpg_sprite_studio.animation.walk import generate_walk
    template, assets = demo()
    template.parameters.arm_swing = template.parameters.leg_swing = template.parameters.bob = 0
    view = template.views[0]
    for layer in view.layers:
        image = Image.new("RGBA", (256, 256))
        image.putpixel((128, 128), (255, 0, 0, 255))
        out = BytesIO()
        image.save(out, format="PNG")
        assets[layer.asset_path] = out.getvalue()
    last = view.layers[-1]
    image = Image.new("RGBA", (256, 256))
    image.putpixel((128, 128), (0, 0, 255, 255))
    out = BytesIO()
    image.save(out, format="PNG")
    assets[last.asset_path] = out.getvalue()
    result = generate_walk(template, assets)
    assert Image.open(BytesIO(result.frames[view.direction][0])).getpixel((128, 128)) == (0, 0, 255, 255)
    # A top-edge upper-body pixel moves outside the canvas during bob.
    head = next(layer for layer in view.layers if layer.part == "head")
    image.putpixel((0, 0), (255, 255, 255, 255))
    out = BytesIO()
    image.save(out, format="PNG")
    assets[head.asset_path] = out.getvalue()
    template.parameters.bob = 6
    assert generate_walk(template, assets).warnings


def test_manifest_load_and_missing_layer(tmp_path):
    from dataclasses import asdict
    from anime_rpg_sprite_studio.animation.templates import load_template
    template, assets = demo()
    path = tmp_path / "template.json"
    path.write_text(json.dumps(asdict(template)), encoding="utf-8")
    for relative, data in assets.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    loaded, decoded = load_template(path)
    assert loaded == template and decoded.keys() == assets.keys()
    next(iter(tmp_path.rglob("*.png"))).unlink()
    with pytest.raises((ValueError, OSError)):
        load_template(path)


def test_apply_walk_roundtrip_relocation_and_v1(tmp_path):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.animation.walk import generate_walk
    service = ProjectService()
    c = service.add_character()
    service.save(tmp_path / "original/project.json")
    template, assets = demo()
    candidate = generate_walk(template, assets)
    assert not c.clips[0].frames
    service.apply_walk(c.id, template, assets, candidate.frames)
    assert len(c.clips[0].frames) == 16 and c.template is not None
    service.save(tmp_path / "copy/project.json")
    service.load(service.path)
    assert service.project.characters[0].template == c.template or service.project.characters[0].template.name == template.name
    assert service.repository.missing_assets(service.project, service.path) == []
    assert len(list((tmp_path / "copy/assets").glob("*.png"))) == 40
    legacy = json.loads(service.path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy["characters"][0].pop("template")
    service.path.write_text(json.dumps(legacy), encoding="utf-8")
    service.load(service.path)
    assert service.project.characters[0].template is None


def test_apply_failure_preserves_original(tmp_path, monkeypatch):
    from anime_rpg_sprite_studio.core.project_service import ProjectService
    from anime_rpg_sprite_studio.animation.walk import generate_walk
    import anime_rpg_sprite_studio.core.project_service as module
    service = ProjectService()
    c = service.add_character()
    service.save(tmp_path / "project.json")
    template, assets = demo()
    candidate = generate_walk(template, assets)
    original = deepcopy(c)
    write = module.write_asset
    counter = [0]
    def failing_write(path, data):
        counter[0] += 1
        if counter[0] == 3:
            raise OSError("disk full")
        write(path, data)
    monkeypatch.setattr(module, "write_asset", failing_write)
    with pytest.raises(OSError):
        service.apply_walk(c.id, template, assets, candidate.frames)
    assert c == original and not list(tmp_path.rglob("*.png"))


def test_layer_loader_rejects_opaque_or_traversing_assets(tmp_path):
    from dataclasses import asdict
    from anime_rpg_sprite_studio.animation.templates import load_template
    template, assets = demo()
    for relative, data in assets.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    path = tmp_path / "template.json"
    path.write_text(json.dumps(asdict(template)), encoding="utf-8")
    first = template.views[0].layers[0]
    Image.new("RGB", (256, 256), "white").save(tmp_path / first.asset_path)
    with pytest.raises(ValueError, match="透明"):
        load_template(path)
    data = asdict(template)
    data["views"][0]["layers"][0]["asset_path"] = "../outside.png"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_template(path)
