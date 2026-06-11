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

### 2026-06-10 — Starlette 1.0.x TemplateResponse API break causes silent Jinja2 LRU TypeError

**Attempted:** Calling `templates.TemplateResponse("template.html", {"request": request, ...})` — the pre-1.0 Starlette API where `name` is the first positional arg and context is a dict containing `request`.

**Why it didn't work:** Starlette 1.0.0 changed `TemplateResponse` to take `request` as the first positional argument. When called with the old signature, Starlette passes the context dict as the template `name` to Jinja2. Jinja2's LRU cache then tries to use the dict as a hash key, raising `TypeError: unhashable type: 'dict'`. The app starts cleanly — the error only surfaces at request time, making it easy to miss in pre-deploy checks.

**What we tried instead:** Updated all `TemplateResponse` calls to the new signature: `templates.TemplateResponse(request, "template.html", {...})` with `request` removed from the context dict. Starlette 1.0+ still makes `request` available inside templates automatically. All 4 failing route tests resolved immediately.

**Status:** Resolved

**Tags:** starlette, jinja2, fastapi, templating, api-break, upgrade, lru-cache, TypeError
