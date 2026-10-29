# Phase 1 implementation plan

Approved specification: architecture proposed in chat on 2026-10-29.
Goal: offline Windows Python 3.12 desktop skeleton; no real API or animation.

Tasks (execute inline, tests before implementation):
1. Define validated models and draft/complete clip validation.
2. Implement versioned JSON repository with atomic replacement and safe asset paths.
3. Define provider, credential and budget protocols; implement deterministic offline Mock.
4. Implement project service and Qt window: project lifecycle, character editing, direction selection.
5. Run full pytest suite and bounded Qt startup smoke test; document remaining limits.

Constraints: CPU only; 256x256 RGBA; four directions x four frames; FPS 8;
no key access/network on startup; no actual billing or credential backend in Phase 1.
Budget contracts: Decimal, USD 5 monthly / 4.50 stop, UTC, reservations,
unknown costs retained, explicit single-use confirmation, no retries.

Ruling: empty directory has no Git repository; work in the user-selected workspace.
No Git commits or worktree creation required. Test runtime uses project-local venv.
Review focus: malformed project data, escaping paths, lost edits, model/UI selection,
and Mock output accidentally appearing to be a real AI animation.

## Execution ledger

All five tasks completed. Final verification: 17 pytest tests passed; editable
installation and pip check passed; Qt event-loop smoke exited 0. Independent
review identified malformed description and non-foot pivot acceptance; both
reproduced by failing tests then fixed. See phase-1-report.md for limitations.
