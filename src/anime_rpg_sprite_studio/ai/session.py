"""Application orchestration. Construct only when AI tools are explicitly opened."""
from pathlib import Path

from ..billing.manager import SQLiteBudgetManager
from ..security.credentials import WindowsCredentialManager
from .fal_provider import FalProvider
from .mock_provider import MockProvider


class AISession:
    def __init__(self, data_dir, credentials=None, http=None, budget=None):
        self.data_dir = Path(data_dir)
        self.credentials = credentials if credentials is not None else WindowsCredentialManager()
        self.budget = budget if budget is not None else SQLiteBudgetManager(self.data_dir / "budget.sqlite3")
        self.fal = FalProvider(self.credentials, self.budget, http=http)
        self.mock = MockProvider()

    def submit(self, request, quote, confirmation):
        rid = self.budget.reserve(quote, confirmation)
        try:
            handle = self.fal.submit(request, rid)
            return rid, handle
        except Exception:
            # Release only if network submission never crossed the durable boundary.
            if self.budget.get(rid)["state"] == "RESERVED":
                self.budget.release_unsubmitted(rid)
            raise
