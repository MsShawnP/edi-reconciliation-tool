# edi-reconciliation-tool — Failure Log

What was attempted that didn't work, why it didn't work, and what was
tried next.

Lower bar than DECISIONS.md — capture failures even when they didn't
produce a durable rule. The whole point: future-you (or future-Claude)
shouldn't re-attempt dead ends because the lesson got lost.

---

## Format

### YYYY-MM-DD — [One-line failure description]

**Attempted:** [What was tried]

**Why it didn't work:** [Concrete reason, not "it broke." If the
failure mode was technical, name the specific issue. If the failure
mode was scope or approach, name that.]

**What we tried instead:** [The next attempt, which may also have
failed and may have its own entry below]

**Status:** Resolved / open / abandoned

**Tags:** [keywords for future text-search — e.g., "rendering, pandoc,
quarto" or "scope, scrollytelling, decoration"]

---

## Entries

### 2026-06-10 — Eager imports in corpus/generator/__init__.py caused RuntimeWarning on `-m` run

**Attempted:** `corpus/generator/__init__.py` imported `CanonicalOrder`, `CorpusError`, etc. directly from `corpus.generator.base` at module level so callers could do `from corpus.generator import CanonicalOrder`.

**Why it didn't work:** When running `python -m corpus.generator.base`, Python first imports the parent package (`corpus.generator.__init__`), which imports `corpus.generator.base`. Then Python tries to set `corpus.generator.base` as `__main__`, but the module is already in `sys.modules` under its package path, not as `__main__`. Python 3.12+ emits: `RuntimeWarning: 'corpus.generator.base' found in sys.modules after import of package 'corpus.generator', but prior to execution of 'corpus.generator.base'; this may result in unpredictable behaviour`.

**What we tried instead:** Moved all imports from submodules to `TYPE_CHECKING` blocks in `__init__.py`. The Protocol and GenerateResult are defined inline; callers import from the submodules directly (`from corpus.generator.base import ...`). No warning.

**Status:** Resolved

**Tags:** python, packaging, module, __main__, TYPE_CHECKING, RuntimeWarning

---

### 2026-06-13 — PowerShell env var syntax silently fails in the Bash tool, causing all tests to skip

**Attempted:** Setting `DATABASE_URL` for pytest using PowerShell syntax inside the Bash tool: `$env:DATABASE_URL="postgresql://..." python -m pytest ...`

**Why it didn't work:** The Bash tool runs bash (POSIX shell), not PowerShell. The `$env:` prefix is PowerShell-specific; bash interprets it as a failed variable expansion and the env var is never set. The test suite treats a missing `DATABASE_URL` as "no DB available" and skips all 28 tests silently — no error, just `28 skipped in 0.06s`. Easy to misread as a successful (empty) run.

**What we tried instead:** Used bash inline env var syntax: `DATABASE_URL="postgresql://..." python -m pytest ...`. All 28 tests ran.

**Status:** Resolved

**Tags:** bash, powershell, env-var, pytest, skip, DATABASE_URL, integration-tests

---

### 2026-06-11 — `fly postgres attach` fails with superuser auth error on managed clusters

**Attempted:** Running `fly postgres attach cinderhaven-db --app edi-reconciliation-tool` to wire DATABASE_URL automatically.

**Why it didn't work:** The Fly CLI's attach command authenticates as the `postgres` superuser using an internal mechanism that expects the cluster's superuser password. On cinderhaven-db, that superuser password differs from the app-user credentials. Error: `500: failed SASL auth (FATAL: password authentication failed for user "postgres")`.

**What we tried instead:** Constructed DATABASE_URL manually using the Fly internal (flycast) hostname and the known `postgres` credentials from the local `.env`. Set with `fly secrets set DATABASE_URL="postgresql://postgres:<password>@cinderhaven-db.flycast:5432/cinderhaven"`. The flycast hostname (`<app>.flycast`) is only reachable within the same Fly organization's private network — correct for app-to-db communication.

**Status:** Resolved

**Tags:** fly.io, postgres, fly-postgres-attach, flycast, secrets, authentication, deploy

---

### 2026-06-10 — Starlette 1.0.x TemplateResponse API break causes silent Jinja2 LRU TypeError

**Attempted:** Calling `templates.TemplateResponse("template.html", {"request": request, ...})` — the pre-1.0 Starlette API where `name` is the first positional arg and context is a dict containing `request`.

**Why it didn't work:** Starlette 1.0.0 changed `TemplateResponse` to take `request` as the first positional argument. When called with the old signature, Starlette passes the context dict as the template `name` to Jinja2. Jinja2's LRU cache then tries to use the dict as a hash key, raising `TypeError: unhashable type: 'dict'`. The app starts cleanly — the error only surfaces at request time, making it easy to miss in pre-deploy checks.

**What we tried instead:** Updated all `TemplateResponse` calls to the new signature: `templates.TemplateResponse(request, "template.html", {...})` with `request` removed from the context dict. Starlette 1.0+ still makes `request` available inside templates automatically. All 4 failing route tests resolved immediately.

**Status:** Resolved

**Tags:** starlette, jinja2, fastapi, templating, api-break, upgrade, lru-cache, TypeError

---

### 2026-06-16 — PowerShell splits `fly ssh console -C` arguments at internal quotes

**Attempted:** Running `fly ssh console -C "python -c '...'"` via the PowerShell tool to query the Fly.io database.

**Why it didn't work:** PowerShell re-parses the `-C` argument at internal quote boundaries, splitting a single string into multiple arguments. `fly ssh console` then errors with "accepts at most 1 arg(s)". This is a PowerShell-specific quoting issue — bash passes the entire string as one argument.

**What we tried instead:** Switched to the Bash tool for all `fly ssh console` commands. Bash handles the nested quoting correctly.

**Status:** Resolved

**Tags:** fly.io, ssh, powershell, quoting, bash, windows

---

### 2026-06-16 — Assumed lifecycle PAID > INVOICED was caused by duplicate data loads; actual cause was 820 RMR grain

**Attempted:** Hypothesized that the PAID inflation was from running the corpus loader multiple times without truncating, resulting in duplicate raw rows.

**Why it didn't work:** Raw table row counts were reasonable (86K rows, avg 101 qty/line = 8.7M cases). The data was not duplicated. The actual cause was the 820 corpus generator emitting one RMR segment per PO line item instead of one per invoice. The `payment_agg` CTE in `int_four_way_match.sql` sums all RMR amounts per invoice, so 18 line-item RMRs inflated the total 18x.

**What we tried instead:** Progressive database investigation — checked raw counts (fine), mart totals (fine), dollar totals (PAID 2.5x INVOICED), then drilled into per-invoice RMR rows to find the grain mismatch. Added a server-side cap and client-side guard while documenting the generator bug for a future fix.

**Status:** Resolved (mitigated; upstream generator fix tracked in docs/finding-820-rmr-grain.md)

**Tags:** 820, RMR, grain, lifecycle, debugging, hypothesis, corpus-generator, int_four_way_match
