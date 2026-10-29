"""CPU silhouette heuristics, never an identity/art-quality guarantee."""
from dataclasses import dataclass
from io import BytesIO
from PIL import Image

from ..core.models import Direction
from ..rendering.sprite_import import normalize_png
from .templates import check_cancel


@dataclass(frozen=True)
class FrameMetrics:
    direction: Direction
    index: int
    bounds: tuple[int, int, int, int] | None
    visible_pixels: int
    opaque: bool


@dataclass(frozen=True)
class QualityWarning:
    code: str
    message: str


@dataclass(frozen=True)
class QualityReport:
    frames: tuple[FrameMetrics, ...]
    warnings: tuple[QualityWarning, ...]


def analyze_frames(frames, cancel=None):
    if set(frames) != set(Direction) or any(set(batch) != {0, 1, 2, 3} for batch in frames.values()):
        raise ValueError("一致性檢查需要四方向完整 16 幀")
    metrics, warnings = [], []
    for direction in Direction:
        group = []
        for index in range(4):
            check_cancel(cancel)
            data = normalize_png(frames[direction][index])
            with Image.open(BytesIO(data)) as image:
                alpha = image.getchannel("A")
                bounds = alpha.getbbox()
                opaque = alpha.getextrema()[0] == 255
                count = 256 * 256 - alpha.histogram()[0]
            item = FrameMetrics(direction, index, bounds, count, opaque)
            metrics.append(item)
            prefix = f"{direction.value.title()} 幀 {index}"
            if bounds is None:
                warnings.append(QualityWarning("empty", f"{prefix}：全透明，沒有可見角色。"))
                continue
            group.append(bounds)
            if opaque:
                warnings.append(QualityWarning("opaque", f"{prefix}：完全不透明，請檢查背景。"))
            if bounds[0] == 0 or bounds[1] == 0 or bounds[2] == 256 or bounds[3] == 256:
                warnings.append(QualityWarning("edge", f"{prefix}：可見內容接觸畫布邊緣，可能已裁切。"))
            if 256 - bounds[3] > 16:
                warnings.append(QualityWarning("foot", f"{prefix}：可見內容距腳底基準超過 16 px；請檢查對齊。"))
            if abs((bounds[0] + bounds[2] - 1) / 2 - 127.5) > 32:
                warnings.append(QualityWarning("offset", f"{prefix}：輪廓水平中心偏離畫布中心超過 32 px。"))
        if len(group) >= 2:
            centers = [(b[0] + b[2] - 1) / 2 for b in group]
            bottoms = [b[3] for b in group]
            widths = [b[2] - b[0] for b in group]
            heights = [b[3] - b[1] for b in group]
            if max(centers) - min(centers) > 6 or max(bottoms) - min(bottoms) > 6:
                warnings.append(QualityWarning("jitter", f"{direction.value.title()}：四幀中心或底部變動超過 6 px，請檢查抖動／腳滑。"))
            if max(widths) - min(widths) > 12 or max(heights) - min(heights) > 12:
                warnings.append(QualityWarning("size", f"{direction.value.title()}：輪廓寬高變動超過 12 px，請人工確認動作或比例。"))
    check_cancel(cancel)
    return QualityReport(tuple(metrics), tuple(warnings))
