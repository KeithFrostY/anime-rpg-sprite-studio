from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    model: str = "mock-placeholder"
    width: int = 256
    height: int = 256
    count: int = 1
    seed: int = 0


@dataclass(frozen=True)
class Quote:
    provider: str
    model: str
    request_fingerprint: str
    estimated_cost: Decimal
    reservation_cost: Decimal
    source: str
    expires_at: datetime
    currency: str = "USD"
    id: str = field(default_factory=lambda: str(uuid4()))
    credential_fingerprint: str = ""
    pricing_unit: str = ""


@dataclass(frozen=True)
class GenerationResult:
    png: bytes
    label: str = "Mock 測試占位圖，非 AI 成果"


@dataclass(frozen=True)
class JobHandle:
    provider: str
    request_id: str
    state: str


class AIProvider(Protocol):
    def capabilities(self) -> dict: ...
    def estimate(self, request: GenerationRequest) -> Quote: ...
    def submit(self, request: GenerationRequest, authorization: str) -> JobHandle: ...
    def get_status(self, handle: JobHandle) -> JobHandle: ...
    def cancel(self, handle: JobHandle) -> JobHandle: ...
    def fetch_result(self, handle: JobHandle) -> GenerationResult: ...
