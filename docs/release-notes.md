# 0.6.0 Windows portable test release

This later internal test build adds single-direction grid/manual slicing and an
offline A/B rig editor, preview and PNG/sprite sheet/JSON export. A/B uses an
independent right-facing workflow; the existing four-direction format remains.
Prepared layers and manual repair of hidden artwork are still required.
The A/B workflow also supports sequential batch export with per-character status,
progress and cancellation; completed character exports are preserved.
The A/B editor includes offline manual masks and paint with editable project
assets; its canvas is limited to four million pixels. Hidden areas require manual art.
The A/B workflow supports per-frame constrained joint and foot corrections,
preserved in schema 5 and used by preview and export.
Schema 6 adds optional cyclic keyframe interpolation; older projects retain
their original per-frame mode until explicitly enabled.

Includes six development phases: project editing, PNG import/preview, CPU layered
animation, PNG/sheet/JSON export, fal.ai adapter with guarded budget flow, and
quality heuristics/onion skin/baseline. Unity integration excluded by request.

On-host verification uses fake credentials and blocked sockets, not a real paid
request. Clean Windows 10/11 VM, real WinVault operations, code signing and live
fal.ai account verification are not claimed. Source and binary versions remain
test quality; pixel/silhouette warnings do not establish identity consistency.

PySide6/Shiboken installed wheel metadata currently supplies commercial-license
text only. The package preserves supplied notices, but does not establish rights
for public redistribution. Verify the wheel source and applicable Qt terms before
any external release. No license purchase or public publication is performed.
