# Phase 1 architecture

UI owns Qt widgets and preview painting. ProjectService owns current project,
file path and dirty state. ProjectRepository owns versioned JSON and atomic writes.
Core dataclasses contain no Qt, networking, credential or billing dependencies.

Direction is front/left/right/back, ordered as future sheet rows. AnimationClip
stores a flat frame list keyed by (direction,index), rather than a mutable nested
mapping; validate() checks duplicates, validate(complete=True) checks all 16 slots.
SpriteFrame enforces 256x256 RGBA metadata and foot-center normalized pivot.
Actual file decoding and RGBA verification belong to Phase 2, not metadata parsing.
Project timestamps are UTC; JSON stores ISO timestamps and relative asset paths.

AIProvider, CredentialManager and BudgetManager are protocols only. No fal.ai
adapter, keyring backend, HTTP client or budget persistence exists in Phase 1.
MockProvider returns deterministic transparent CPU placeholders, never character
animation. UI does not insert its demonstration image into project frame lists.

Phase 5 must use per-request explicit confirmation, official expiring price
quotes, Decimal reservations and durable unknown-cost tracking. No price is
hardcoded here. Budget limits do not guarantee supplier-side billing caps.

UI reads/writes small JSON projects synchronously in Phase 1. Future image work
and HTTP must run outside the GUI thread using Qt signal delivery. Generating
animations and requesting AI images remain separate services.

Phase 2: SpriteWorker validates/normalizes PNG with Pillow in a thread pool.
Only PNG bytes cross the worker boundary; QPixmap is constructed on the UI thread.
Tokens bind results to epoch/project object/character/direction/project path.
Stale results never write files. QTimer drives four cached frames, while direction
and character changes stop playback and reset the current slot.

ProjectService.import_frames consumes normalized bytes from this trusted decoder;
it is not an arbitrary-image public import endpoint. Unique asset names and rollback
keep previous frame references intact on partial failure. Old referenced assets
are not deleted, preserving saved drafts and allowing safe discard.
Save-as stages uniquely named referenced assets and atomically saves JSON last;
failure removes newly staged files and retains the original project/path.
Small file writes remain synchronous; decoding and normalization run off the UI.

Phase 3 adds optional Character.template in schema 2. Repository migrates schema 1
to schema 2 and uses asset_references() for frames and rig layers consistently.
CharacterTemplate holds four ordered six-layer views plus bounded walk parameters;
image joint coordinates use top-left origin, distinct from engine pivot coordinates.

animation/templates validates local manifests, resolves only in-root PNG files,
normalizes transparent RGBA layers, and provides a diagnostic CPU mannequin.
animation/walk has no Qt or AI imports. It uses padded 768x768 intermediate images,
joint-centered bicubic rotation, upper-body displacement and alpha compositing,
then crops 256x256 output and returns clipping warnings. Cancellation uses Event.

TemplateDialog is modal, binds its original project/character/path, and stores only
in-memory candidates. TemplateWorker loads/generates in the thread pool; monotonically
increasing job IDs reject stale/cancelled/closed results. Changing parameters clears
candidates. User-confirmed apply_walk stages layer and frame assets, updates model
only after all writes succeed, and preserves original references on failure.
Candidate FPS belongs to clip and does not require regeneration. Main-window preview
workers are invalidated before opening the dialog and refreshed after it closes.

Phase 4 export is engine-independent. capture_export copies current character
metadata and creates frozen frame references; prepare_export resolves/decodes all
16 PNGs into immutable normalized bytes. No project mutation or forced save occurs.
ExportWorker does preparation, composition, disk writes and output verification
outside the GUI thread. Source images are not reread after preparation unless the
user revalidates. Sheet paste has no alpha mask, preserving semi-transparent RGBA.

export_bundle creates a private TemporaryDirectory under the user-selected parent,
writes 16 PNGs + sheet + JSON, checks file formats/pixels/metadata, then publishes
via Windows no-replace directory rename to a UUID output folder. No work or callbacks
after publication may turn a completed export into cancellation. ExportDialog waits
for worker settlement on close and propagates successful paths even for late cancel.
Export JSON format_version=1 is independent of project schema_version=2, contains
portable relative output paths and explicit coordinate origins. No Unity code exists.

Phase 5 introduces AISession outside core. It lazily creates the local SQLite
ledger and explicit WindowsCredentialManager only on opening AI tools. Default UI
provider remains Mock. No startup credential/network operations. FalProvider uses
injected HTTP for tests and SafeHttp (urllib, verified TLS/no redirects/no retries)
for production; authenticated API hosts and unauthenticated media hosts are separate.

SQLiteBudgetManager stores Decimal strings, quoted request/key fingerprints,
single-use hashed confirmation tokens and durable requests/events. BEGIN IMMEDIATE
serializes reserve/claim/reconcile across instances. SUBMITTING is committed before
POST; any ambiguous outcome retains fees. Independent billing_unresolved flag cannot
be cleared by a COMPLETED queue status. Matching new ambiguous billing evidence sets
that flag before parsing; historical confirmed amounts remain preserved. Reservations
and claims both gate on other active/unsettled requests and current month allowance.

Live rates come only from authenticated official pricing endpoint, short TTL, with
known USD image/megapixel units; no static currency rate. Invoice synchronization
requires complete matching per-request billing events; missing data is never zero.
AIDialog explicitly obtains confirmation before reserve/submit, makes manual recovery
operations in AIWorker, and never inserts generated candidates into animation frames.
All AIWorker errors are generic, avoiding raw HTTP/key exception leakage.

Phase 6 quality analysis is a pure Pillow heuristic over 16 normalized frames.
QualityDialog runs it in a background worker and waits on close/cancel. It never
modifies pixels. Shared Preview renders optional baseline and 20%-opacity neighbors
onto its own widget only; neither generation nor export imports that widget.

runtime.resource_path resolves bundled documents/examples via sys._MEIPASS or the
source tree. Startup installs a generic exception hook without raw API exception
text. Normal startup remains offline; optional --self-test-report launches a
guarded diagnostic workflow, blocks Python TCP/DNS/UDP and actual WinVault methods,
and uses temporary data only. The onedir PyInstaller spec explicitly collects
Windows keyring imports and metadata and only bounded user-facing resources.
Build subprocess PATH is isolated to Python and Windows to avoid host tool DLL
aliases shadowing OS libraries. On-host frozen-app validation is separate from
future clean Windows/environment and licensing/public-release checks.
