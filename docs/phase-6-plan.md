# Phase 6 implementation plan

Approved goal: Windows portable test release with CPU quality checks and preview aids.
No Unity, local models, GPU or paid API verification. Existing workspace has no Git.

Tasks:
1. Test-first `animation/quality.py`: analyze complete 16 PNG frames using alpha
   bounds; flag empty/opaque/edge-touching content, foot-distance and within-direction
   center/bottom/size changes. Heuristics only, no identity judgement or correction.
2. Preview baseline and previous/next onion skin in main/candidate views; test actual
   widget pixels. Display only; generated/exported PNGs must remain unchanged.
3. Background QualityDialog for current clip/candidate, table + readable warnings,
   cancellation and safe close; invalid/missing assets reported without project changes.
4. Startup exception handler with fixed generic error text (never raw API secrets),
   repeated open/close and timed playback regression tests.
5. PyInstaller Windows onedir spec, explicit keyring Windows hidden imports, bounded
   bundled docs and six-layer example only. No ledger/keys/tests/venv in release.
   Build under ignored build/dist; fresh versioned directories, no destructive cleanup.
6. Offline packaged self-test opt-in CLI: block sockets and real vault operations,
   create temp project, load shipped template, generate/apply/save/reopen, preview,
   analyze and export, Mock, fake-vault keyring interface, write pass/fail report.
   Never run self-test automatically or use it to contact fal.ai.
7. Run pytest, built EXE self-test and GUI startup, inspect screenshot and output
   dependencies; assemble zip + SHA256 + licenses/notices/manual and report.

Review focus: aids altering source images; quality false positives; missing packaged
DLLs/plugins/resources; secrets/ledgers in bundle; no network in startup/self-test;
worker lifetime on close. Clean Windows 10/11 matrix and code signing are out of
available host verification, report explicitly rather than claim compatibility.

Decisions: alpha bbox uses nonzero alpha; warn on actual edge contact, foot distance
>16 px, center/bottom jitter >6 px and size change >12 px within one direction.
No cross-direction silhouette equality requirement. Package is unsigned onedir,
not installer/onefile. PyInstaller is build-only dependency. On-host packaged
verification does not replace a clean VM test. User files stay outside app folder.

Packaging regression: first EXE failed to import QtWidgets (DLL procedure missing).
Source runtime loads Windows System32/icuuc.dll; PyInstaller picked an incompatible
Poppler ICU78 alias from inherited PATH. Rebuild uses an isolated tool/Windows PATH
to resolve system DLLs correctly, not an ad-hoc copy of unrelated ICU libraries.

## Execution ledger

Tasks 1–7 completed. Eight new tests; full suite 102 passed in 25.83s.
Source self-test passed. First frozen run failed before report; stderr showed
QtWidgets DLL procedure failure. Isolated PATH rebuild fixed the reproduced
native dependency regression; final EXE exited 0 with frozen=true report.
Independent review DNS/UDP guard finding reproduced with fake resolver/sendto,
fixed RED→GREEN; full suite green. No other important findings reported.
ZIP integrity/hash/resources/privacy checks passed. Native screenshot inspected.
Final verified artifact: dist/20261029-132924-953507. Source/EXE reports and known
limits documented in phase-6-report.md. No clean VM or real-vault/API claims.
