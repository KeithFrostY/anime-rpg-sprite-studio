from pathlib import Path
from copy import deepcopy
from uuid import uuid4
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from .models import Project, Character, SpriteFrame, Direction, utc_now, asset_references
from .assets import write_asset
from .project_repository import ProjectRepository


class ProjectService:
    def __init__(self):
        self.repository = ProjectRepository()
        self.project = Project()
        self.path: Path | None = None
        self.dirty = False

    def new(self):
        self.project = Project()
        self.path = None
        self.dirty = False

    def add_character(self) -> Character:
        character = Character()
        self.project.characters.append(character)
        self.project.active_character_id = character.id
        self.dirty = True
        return character

    def save(self, path: Path):
        path = Path(path).resolve()
        candidate = deepcopy(self.project)
        created = []
        candidate.updated_at = utc_now()
        try:
            if self.path and self.path.parent.resolve() != path.parent:
                refs = list(asset_references(candidate))
                originals = [ref.asset_path for ref in refs]
                paths = {}
                for original in originals:
                    if original in paths:
                        continue
                    source = self.repository._asset(self.path.parent, original)
                    data = source.read_bytes()  # Missing source fails before JSON replacement.
                    relative = f"assets/{uuid4().hex}.png"
                    target = self.repository._asset(path.parent, relative)
                    write_asset(target, data)
                    created.append(target)
                    paths[original] = relative
                for ref, original in zip(refs, originals):
                    ref.asset_path = paths[original]
            self.repository.save(candidate, path)
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
        # Preserve character references when no relocation occurred.
        if created:
            self.project = candidate
        else:
            self.project.updated_at = candidate.updated_at
        self.path = Path(path)
        self.dirty = False

    def import_frames(self, character_id: str, direction: Direction, images: dict[int, bytes]):
        if self.path is None:
            raise ValueError("請先儲存專案")
        character = next(c for c in self.project.characters if c.id == character_id)
        if not images or any(type(i) is not int or not 0 <= i < 4 for i in images):
            raise ValueError("Invalid frame slots")
        created = []
        frames = []
        try:
            for index, data in images.items():
                relative = f"assets/{uuid4().hex}.png"
                frame = SpriteFrame(asset_path=relative, direction=direction, index=index)
                target = self.repository._asset(self.path.parent, relative)
                write_asset(target, data)
                created.append(target)
                frames.append(frame)
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
        clip = character.clips[0]
        clip.frames = [f for f in clip.frames if not (f.direction == direction and f.index in images)] + frames
        self.dirty = True

    def frame_bytes(self, character_id: str, direction: Direction) -> dict[int, bytes]:
        if self.path is None:
            return {}
        character = next(c for c in self.project.characters if c.id == character_id)
        return {f.index: self.repository._asset(self.path.parent, f.asset_path).read_bytes()
                for f in character.clips[0].frames if f.direction == direction}

    def apply_walk(self, character_id, template, assets, frames):
        """Commit a validated candidate as one in-memory transaction after staging."""
        if self.path is None:
            raise ValueError("請先儲存專案")
        template = deepcopy(template)
        template.validate()
        character = next(c for c in self.project.characters if c.id == character_id)
        if set(frames) != set(Direction) or any(set(batch) != {0, 1, 2, 3} for batch in frames.values()):
            raise ValueError("Candidate must contain all 16 frames")
        required = {layer.asset_path for view in template.views for layer in view.layers}
        if not required.issubset(assets):
            raise ValueError("Missing template assets")
        created, new_frames = [], []
        def stage(data):
            relative = f"assets/{uuid4().hex}.png"
            target = self.repository._asset(self.path.parent, relative)
            write_asset(target, data)
            created.append(target)
            return relative
        try:
            paths = {relative: stage(assets[relative]) for relative in sorted(required)}
            for view in template.views:
                for layer in view.layers:
                    layer.asset_path = paths[layer.asset_path]
            for direction in Direction:
                for index in range(4):
                    relative = stage(frames[direction][index])
                    new_frames.append(SpriteFrame(asset_path=relative, direction=direction, index=index))
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
        character.template = template
        character.clips[0].frames = new_frames
        self.dirty = True

    def load(self, path: Path):
        project = self.repository.load(path)
        self.project = project
        self.path = Path(path)
        self.dirty = False

    def apply_ab_walk(self, character_id, rig, assets):
        """Validate and stage a candidate before replacing its A/B rig."""
        if self.path is None:
            raise ValueError('請先儲存專案')
        candidate = deepcopy(rig)
        candidate.validate()
        character = next(c for c in self.project.characters if c.id == character_id)
        refs = [(candidate.source, 'original')]
        for layer in candidate.layers:
            refs.append((layer, 'layer'))
            if layer.edit is not None:
                refs.extend(((layer.edit.source, 'edit_source'), (layer.edit.mask, 'mask'), (layer.edit.paint, 'paint')))
        for ref, role in refs:
            data = assets.get(ref.asset_path)
            if not isinstance(data, bytes) or len(data) > 32 * 1024 * 1024:
                raise ValueError('缺少素材或圖片檔案過大')
            try:
                with Image.open(BytesIO(data)) as image:
                    if image.format != 'PNG' or image.width * image.height > 32_000_000 or getattr(image, 'n_frames', 1) != 1:
                        raise ValueError('素材必須是單張 PNG')
                    if role != 'original' and image.size != tuple(candidate.canvas):
                        raise ValueError('素材必須與畫布尺寸一致')
                    if role in ('layer', 'paint') and ('A' not in image.getbands() and 'transparency' not in image.info):
                        raise ValueError('分件必須是同畫布尺寸的透明 PNG')
                    if role == 'mask' and image.mode != 'L':
                        raise ValueError('遮罩必須是灰階 PNG')
                    image.load()
            except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
                raise ValueError('無法讀取 PNG 素材') from exc
        created = []
        try:
            paths = {}
            originals = [ref.asset_path for ref, role in refs]
            for original in originals:
                if original not in paths:
                    relative = f'assets/{uuid4().hex}.png'
                    target = self.repository._asset(self.path.parent, relative)
                    write_asset(target, assets[original]); created.append(target)
                    paths[original] = relative
            for (ref, role), original in zip(refs, originals):
                ref.asset_path = paths[original]
            candidate.validate()
        except Exception:
            for target in created: target.unlink(missing_ok=True)
            raise
        character.ab_walk = candidate
        self.dirty = True
