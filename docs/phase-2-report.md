# Phase 2 completion report — 2026-10-29

## Completed

- Single or four-PNG import with explicit direction/slot mapping confirmation.
- CPU/background decoding, strict 256x256 single-image PNG, RGBA normalization,
  alpha preservation and 8 MiB input bound. No scaling or background removal.
- Project-local unique assets, all-or-nothing frame reference updates, rollback.
- Save-as copies referenced assets; missing source/write failure preserves original.
- Four clickable thumbnails, manual frame selection, playback/pause, FPS updates.
- Character/direction switch stops playback/reset; stale worker results ignored.
- Four valid frames in selected direction required for playback; bad/missing assets
  disable playback and show errors. Other directions can remain drafts.

## Changed files

- core/assets.py (new), core/project_service.py
- rendering/sprite_import.py (new)
- ui/sprite_worker.py (new), ui/main_window.py
- tests/test_phase2.py, tests/smoke_phase2.py (new)
- README.md, docs/architecture.md
- docs/phase-2-plan.md, phase-2-report.md, phase-2-preview.png (new)

## Verification

Initial Phase 2 tests: seven expected failures before implementation.
Full suite: 29 passed in 0.88s (Python 3.12 / Windows / PySide6).
Tests cover format/size rejection, alpha/RGB conversion, import rollback,
save-as relocation/failure, dialog mapping, stale results, direction reset and FPS.
Independent review found Mock mutation of cached pixmap and save invalidating
pending import; both reproduced with regression tests, fixed, full suite green.
Actual Qt event-loop smoke generated diagnostic fixtures, loaded all 16 frames,
switched all four directions, exercised playback cycles, captured screenshot and
exited normally. Screenshot visually inspected. pip check passed.
No real AI requests, credentials, GPU or model downloads.

## Remaining / risks

- Phase 3–6 intentionally absent. No animation generation/export/real API yet.
- No sheet splitting, free-form resizing or automatic alignment.
- Old/unused images are retained for draft safety; repeated replacement grows assets/.
- A process crash during asset staging can leave orphan files; saved JSON remains
  atomic, but asset garbage collection is not implemented.
- Small asset writes/save-as copies run synchronously; future larger workloads need
  cancellable background persistence. Qt timers are preview timing, not a real-time guarantee.
- Full manual Windows file-dialog, high-DPI and multi-monitor matrix not executed.
- Current preview decodes an entire direction as one unit; one bad frame disables
  that direction until replaced, rather than showing partial decoded thumbnails.

Next recommendation: user acceptance of import/playback, then separate Phase 3
design for explicit layered CPU templates. Do not start Phase 3 automatically.
