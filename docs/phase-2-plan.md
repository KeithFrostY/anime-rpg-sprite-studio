# Phase 2 plan

Approved in chat: PNG import and four-direction playback. CPU/offline only.
1. Tests first: strict PNG dimensions, RGBA conversion, transaction failure,
   asset relocation, four-slot playback and direction reset.
2. Pillow decoder returns immutable PNG bytes off the GUI thread.
3. ProjectService commits validated bytes to unique project-relative assets;
   update frames only after all writes succeed. Save-as copies referenced assets.
4. Qt worker delivers decoded data; UI checks project/character/direction token.
5. Qt timer plays only four valid decoded frames, supports pause and manual slots.
6. Run full suite and GUI smoke, independent review, completion report.

Single imports target the selected slot. Four-file imports use file-dialog order,
explicitly shown in a confirmation dialog. No rescaling/background removal.
Import requires a saved project. Switching direction/character stops at slot 0.
Save-as fails on missing source assets rather than silently creating broken copies.

## Execution ledger

Tasks 1–6 complete: full suite 29 passed; four-direction Qt smoke passed.
Independent review regressions: isolated Mock QPixmap from cached animation;
same-path save no longer invalidates imports; save-as blocked during import.
Ruling: keep retired asset files for saved-draft safety; no automatic deletion.
