from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from ..ai.contracts import Quote

MONTHLY_LIMIT = Decimal("5.00")
SAFETY_LIMIT = Decimal("4.50")


@dataclass(frozen=True)
class MonthSummary:
    utc_month: str
    confirmed: Decimal
    pending_reservations: Decimal
    available: Decimal


class BudgetManager(Protocol):
    """Phase 5 transaction boundary; not a supplier billing guarantee.

    Confirmation is single-use and bound to quote fingerprint. Unknown costs
    retain reservations across restart/month boundaries. At most one paid job;
    no automatic retry. Quotes need current official source and expiration.
    """
    def get_month_summary(self, utc_month: str) -> MonthSummary: ...
    def register_quote(self, quote: Quote) -> None: ...
    def confirm_quote(self, quote_id: str) -> str: ...
    def validate_quote(self, quote: Quote) -> None: ...
    def reserve(self, quote: Quote, confirmation: str) -> str: ...
    def claim(self, request_id: str, fingerprint: str, credential: str) -> None: ...
    def mark_submitted(self, reservation_id: str, provider_request_id: str) -> None: ...
    def mark_unknown(self, request_id: str, reason: str) -> None: ...
    def reconcile(self, request_id: str, actual_cost: Decimal, evidence: str, billing_at=None) -> None: ...
    def release_unsubmitted(self, reservation_id: str) -> None: ...
