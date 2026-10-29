from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from PIL import Image, ImageDraw
from .contracts import GenerationRequest, GenerationResult, JobHandle, Quote


class MockProvider:
    """Synchronous, CPU-only diagnostic image. No credential or network access."""
    def __init__(self):
        self._results: dict[str, GenerationResult] = {}

    def capabilities(self) -> dict:
        return {"provider": "mock", "models": ["mock-placeholder"], "paid": False}

    def _validate(self, request):
        if request.model != "mock-placeholder" or (request.width, request.height, request.count) != (256, 256, 1):
            raise ValueError("Mock supports one 256x256 placeholder only")

    def estimate(self, request: GenerationRequest) -> Quote:
        self._validate(request)
        return Quote("mock", request.model, sha256(repr(request).encode()).hexdigest(),
                     Decimal("0"), Decimal("0"), "offline mock", datetime.now(timezone.utc) + timedelta(minutes=5))

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self._validate(request)
        image = Image.new("RGBA", (256, 256))
        draw = ImageDraw.Draw(image)
        draw.ellipse((96, 32, 160, 96), fill=(230, 180, 140, 255))
        draw.rectangle((88, 96, 168, 192), fill=(90, 110, 210, 255))
        draw.rectangle((96, 192, 120, 255), fill=(60, 60, 80, 255))
        draw.rectangle((136, 192, 160, 255), fill=(60, 60, 80, 255))
        draw.text((8, 8), "MOCK", fill="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return GenerationResult(buffer.getvalue())

    def submit(self, request: GenerationRequest, authorization: str = "") -> JobHandle:
        result = self.generate(request)
        key = sha256(repr(request).encode()).hexdigest()
        self._results[key] = result
        return JobHandle("mock", key, "SUCCEEDED")

    def get_status(self, handle: JobHandle) -> JobHandle:
        self.fetch_result(handle)
        return handle

    def cancel(self, handle: JobHandle) -> JobHandle:
        return self.get_status(handle)  # Already completed locally; no charge exists.

    def fetch_result(self, handle: JobHandle) -> GenerationResult:
        if handle.provider != "mock":
            raise ValueError("Wrong provider")
        return self._results[handle.request_id]
