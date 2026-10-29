# Phase 3 implementation plan

Approved design: six pre-aligned transparent PNG layers per direction; CPU
four-pose walking generator; candidate preview followed by explicit apply.

Goal: repeatable offline layered template animation without changing existing
Walk frames until successful apply. Python 3.12, PySide6, Pillow, pytest.

## Tasks and contracts

1. `core/rig.py`: Layer(part,asset_path,joint), TemplateView(direction,layers),
   WalkParameters(arm_swing=12,leg_swing=10,bob=2), CharacterTemplate.
   Exactly head/body/left_arm/right_arm/left_leg/right_leg per view; four views.
   Joints use top-left image coordinates, integer 0..255. Array order is back-to-front.
   Parameters: arm 0..30 degrees, leg 0..25 degrees, bob 0..6 pixels.
2. `animation/templates.py`: load external JSON manifest or built-in diagnostic
   template; validate/decode 24 single-frame 256x256 transparent RGBA PNG layers
   and safe local relative paths. No network, mirroring or layer inference.
3. `animation/walk.py`: deterministic padded Pillow transforms and compositing.
   Four phases (+1,0,-1,0), opposing arms/legs; upper body bob (0,-bob,0,-bob).
   Output four directions x four 256x256 RGBA PNGs. Warn when content clips.
   Cancellation checked between layers/frames; cancelled work has no project writes.
4. Schema 2 adds optional Character.template; read schema 1 projects with defaults.
   Repository includes layer assets in missing checks. Save-as copies all references.
   `ProjectService.apply_walk` stages unique layer/frame files, then updates model
   atomically; any write failure retains original template and frames.
5. `ui/template_dialog.py`, worker: load/demo, parameter controls, generate/cancel,
   four-direction candidate preview/slots/playback/FPS, explicit apply confirmation.
   Modal dialog binds project and character; main preview loads invalidated first.
   Parameter/template changes clear candidates; only latest worker result accepted.
6. Full regression suite, timed Qt smoke, independent code review and report.

## Test cycle

Write test functions before implementation, run to see missing functionality,
implement, rerun. Core tests cover bad/missing layers, joint range/nonfinite values,
paths, parameters, compositing order, deterministic output, cancellation, clipping,
schema migration, asset relocation and staged-write rollback. GUI tests cover
generation without replacement, apply/cancel, stale result and candidate invalidation.

## Review focus

No saved frame loss on failure; no candidate reuse after changed settings; closing
while worker runs must not mutate project; external paths remain under template
root; schema-1 projects remain readable with no template.

## Execution ledger

Ruling: continue in existing user workspace without Git (no repository present).
Ruling: template/joint editing uses documented JSON; no graphical rig editor in
this phase. Built-in template is clearly diagnostic art, not AI anime output.
Ruling: old files retained to preserve saved drafts, as in Phase 2.

### Completed

- Task 1–4: model/loader/generator/persistence tests RED→GREEN; legacy regression suite passed.
- Task 5: candidate UI tests RED→GREEN; verified no project mutation until apply.
- Task 6: 47 pytest tests passed (21.76s); pip check clean; real Qt smoke PASS.
- Final review: independent read-only reviewer found import-error template button
  remained disabled. Fixed with test_failed_png_import_restores_template_button
  RED→GREEN; full suite green. No other important findings reported.
- Generated and visually inspected docs/phase-3-preview.png; included usable example
  manifest and 24 diagnostic PNGs. Details and known limitations in phase-3-report.md.
