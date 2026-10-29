# Phase 5 implementation plan

Approved: one fal.ai FLUX.1 Schnell provider, Windows keyring, SQLite Decimal
budget, explicit single-request confirmation, offline Mock GUI and fake-HTTP tests.
No live key or paid requests during development or verification.

Tasks (test first):
1. WindowsCredentialManager explicitly selects WinVaultKeyring, lazy access,
   injectable test backend, sanitized errors, fal-only, masked GUI.
2. SQLiteBudgetManager: quotes, single-use hashed confirmations, requests, audit
   events; BEGIN IMMEDIATE; Decimal strings; UTC month; 4.50 threshold / 5 budget.
   RESERVED -> SUBMITTING durable boundary before network. Unknown costs block
   new reservations across restart/months. Only RESERVED can be released.
3. HTTPS transport using stdlib urllib (no new dependencies): no redirects/retries,
   verified TLS, no environment proxy, fixed API hosts, bounded reads, generic errors.
   Media downloads only fal.media/subdomains, never include credentials.
4. FalProvider: request fixed to 256x256, one PNG, 4 steps, safety checker on;
   current official unit price, 2-minute quote, conservative full billing unit;
   reject unknown currencies/units. Bind quote to exact request and key hash.
   Adapter consumes reservation before one POST; ambiguous errors retain fees.
   Manual status/result/cancel operations; billing-event reconciliation never treats
   missing rows as zero. No automatic submit/retry/model switching.
5. Modal AI dialog: default Mock; masked key add/test/change/delete; quote preview
   then explicit Yes confirmation; background jobs; budget/history and selected
   request recovery/cancel/billing sync; separate candidate save, never frame import.
   Persistent app data initialized only on opening AI tools, not application startup.
6. Fake-key/fake-transport tests (network forbidden), full regression suite, GUI
   smoke, review, price/security usage documentation and completion report.

Review focus: crash after POST, multiple processes, quote/key changes, expired
confirmation, Decimal NaN/float inputs, month boundary, leaked error text, redirects,
unknown cost and cancelled request release. No claim of supplier hard spending cap.

Decisions: unit-based estimates use one full image/megapixel for one 256x256 image,
not historical averages; no hardcoded monetary rate. If a billing key lacks scope,
leave unresolved and block new paid submissions. No manual zero-cost override.
Official docs reviewed 2026-10-29: /models/pricing, /models/billing-events,
platform authentication, queue submit-path/status/result/cancel, model schema.
Continue existing workspace without Git. Tests inject temp data directories and
fake credentials; no real WinVault read/write or real HTTP is exercised.

## Execution ledger

Tasks 1–6 completed. Final full suite: 94 passed in 25.68s; compileall/pip check clean.
Actual Qt smoke with blocked sockets/fake vault/fake HTTP: PASS; screenshot inspected.
Independent review found later cross-month adjustments could leave old fees settled.
Fixed via RED→GREEN regression: independent billing_unresolved persisted, new matching
ambiguous evidence blocks, and claim rechecks all other unsettled requests. Status
COMPLETED cannot clear that flag. Full suite green after fix.
No real credential operations or paid requests. Known limitations and decisions,
including missing-ID lockout and billing permissions, documented in phase-5-report.md.
