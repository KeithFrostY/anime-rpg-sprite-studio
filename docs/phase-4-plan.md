# Phase 4 implementation plan

Approved scope: current character's independent PNGs, 1024x1024 RGBA sheet,
versioned animation JSON, GUI export/progress/cancel/open-folder. No Unity.
Use existing Python 3.12, Pillow, PySide6, pytest. No new services/dependencies.

## Tasks

1. Write core export tests before implementation. `capture_export(character,path)`
   captures immutable metadata and 16 frame references; rejects incomplete clips.
2. `prepare_export(snapshot,cancel,progress)` validates safe in-root paths and all
   16 single-frame 256x256 PNGs in background, returns immutable normalized bytes.
3. `export_bundle(bundle,parent,cancel,progress)` builds frames/, walk_sheet.png,
   animation.json in a private sibling temporary directory, validates outputs,
   then atomically renames to a fresh walk-<uuid> directory. Existing outputs are
   never replaced on target Windows. Failure/cancel before publication cleans up.
4. JSON format v1: FPS, rational 1/FPS duration, loop, direction order, filenames,
   sheet top-left rects and bottom-left normalized pivot (0.5,0).
5. ExportWorker + modal ExportDialog: prepare before enabling export; parent folder,
   status/progress/cancel/open-folder. Snapshot never changes source project.
   Closing while busy requests cancellation and waits for worker settlement.
   A cancellation arriving after atomic publication reports completed export.
6. Main window export entry available only for saved complete clip and no import.
   Tests, real Qt smoke, independent review, docs and completion report.

## Verification

Tests: unique per-cell pixels and alpha, PNG dimensions, JSON FPS/loop/coordinates,
missing/corrupt/wrong-sized assets, snapshot isolation, existing output protection,
cancellation before/mid-work, write/rename failure cleanup, GUI readiness and cancel.
Run full suite, pip check, Qt smoke with actual export, inspect screenshot/sheet.

## Review focus

Commit/cancel race; no source paths/secrets in JSON; source/project untouched;
no replacement/deletion of unrelated directories; all 18 output files validated.

## Decisions

- Continue existing workspace, no Git repository/commits.
- Always export all three formats together (16 PNG + sheet + JSON).
- Export captures current in-memory metadata, including unsaved FPS/name changes;
  a saved project location is required for frame paths. Export never saves project.
- Use fresh UUID output folder; no overwrite prompt or destructive replacement.
- Small bounded output validation is done in worker before final rename. Native
  folder opening uses Qt desktop services only on explicit user click.

## Execution ledger

Tasks 1–6 complete. Core 11 tests RED→GREEN, GUI 4 tests RED→GREEN; added
late-commit GUI cancellation coverage. Full suite 63 passed in 23.84s.
Independent read-only review: no important bugs; native close while busy verified.
Real Qt prepare/export smoke PASS; 18-file example retained and screenshot/sheet
visually inspected. compileall/pip check clean. No dependencies or API calls added.
See phase-4-report.md for files, decisions, limitations and next-phase boundary.
