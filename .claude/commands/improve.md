---
description: Review and improve an existing project. Audits code, workflow files, and structure, then guides you through fixing what matters.
---

Run a guided improvement pass on this project. Works on any project
that already has code or files — this is for making existing things
better, not starting from scratch.

Argument: $ARGUMENTS

**Modes:**
- `/improve` — full workflow: audit + plan + fix + track
- `/improve audit-only` — audit and report only, no fixes. Good for
  regular health checks or deciding which project needs attention.
- `/improve [topic]` — focus the improvement on a specific area
  (e.g., `/improve tests` or `/improve the data pipeline is flaky`)

If $ARGUMENTS contains "audit-only" or "audit only", run in
audit-only mode: Steps 1-4 only, then log the audit in Step 7
and stop. Do not create an improvement arc or execute fixes.

If $ARGUMENTS contains anything else, treat it as context for what
the user wants to focus on.

If $ARGUMENTS is empty, run the full check-in + audit + improve flow.

## Step 1: Check for workflow files

Look for these files in the project root:
- CLAUDE.md, PLAN.md, HANDOFF.md, DECISIONS.md, FAILURES.md

If none exist, tell the user:
> "This project doesn't have workflow files yet. I can add them first
> so we can track what we improve. Want me to run /add-workflow to
> set that up, then come back to the improvement pass?"

If the user says yes, run /add-workflow first, then return to Step 2.
If the user says no, continue without workflow files — you can still
audit and improve, you just won't have PLAN.md to write the
improvement arc into.

## Step 2: Quick check-in

Ask these three questions. Ask them one at a time — wait for each
answer before asking the next.

1. "What's bugging you about this project right now? Anything you've
   been putting off or that doesn't feel right?"

2. "Is there a part of the code you're least confident about — like
   something that works but you're not sure why, or something you'd
   be nervous to change?"

3. "Anything you want me to NOT touch? (Files, features, or areas
   that should stay as-is.)"

If $ARGUMENTS was provided, you can fold it into the first question:
"You mentioned [argument]. Tell me more about that — and is there
anything else bugging you?"

Keep their answers. You'll merge them with audit findings in Step 4.

## Step 3: Audit the project

Read through the project and assess each category below. For each
item, note whether it's fine, needs attention, or is missing entirely.

Be thorough but don't manufacture problems. If something works and
is clear, say so.

### 3a. Workflow files (skip if project has none)

- **CLAUDE.md:** Is the project description filled in? Stack section?
  Voice section? Or is it still the template with brackets?
- **PLAN.md:** Is there an active arc? Are tasks specific and
  actionable? Any stale checked/unchecked items from weeks ago?
- **HANDOFF.md:** When was the last entry? Is there uncommitted work
  that happened since then?
- **DECISIONS.md:** Any decisions logged? Anything in the code that
  clearly represents a choice but isn't documented here?
- **FAILURES.md:** Any entries? Is the project old enough that the
  absence of failure entries suggests they're not being captured?

### 3b. Code quality

- **File organization:** Are files in sensible locations? Any loose
  scripts in the root that should be in src/ or similar?
- **Naming:** Are files, functions, and variables named clearly enough
  that you can tell what they do without reading the body?
- **Dead code:** Anything commented out or obviously unused?
- **Duplication:** Any copy-paste patterns that should be a shared
  function?
- **Error handling:** Are errors handled at system boundaries (user
  input, file I/O, API calls)? Ignore internal code — only check
  boundaries.

### 3c. Tests

- Do tests exist? If yes, do they run and pass?
- Are the most important code paths tested?
- If no tests exist, identify the 2-3 things that should be tested
  first. Not everything — just the highest-value targets.

### 3d. Dependencies

- Are dependencies declared (package.json, requirements.txt,
  renv.lock, Gemfile, etc.)?
- Anything obviously outdated or pinned to a version with known
  issues?

### 3e. Documentation

- Is there a README? Does it explain what the project is and how to
  run it?
- Could someone else (or you in 3 months) pick this up and get it
  running without asking you questions?

### 3f. Git hygiene

- Any uncommitted changes sitting around?
- Any large files tracked in git that shouldn't be (data files,
  binaries, node_modules)?
- Is .gitignore reasonable for the project type?

### 3g. Deep reviews (automated)

After the manual audit above, run these automated reviews to catch
things a read-through might miss. These are skills that use
specialized reviewers — they go deeper than the checks above.

1. **Security review:** Run /security-review on the project. This
   checks for vulnerabilities, exposed secrets, hardcoded
   credentials, input validation gaps, auth/authorization issues,
   and OWASP top 10 risks. If the project handles user data, API
   keys, or any external input, this matters.

2. **Code quality review:** Run /ce:review on the project. This
   uses multiple specialized reviewers (correctness, maintainability,
   testing, performance, and more) to find issues the manual audit
   missed. It produces structured findings with confidence ratings.

3. **Data and analysis review (if applicable):** If the project does
   any math, calculations, data transformations, statistical analysis,
   aggregations, or metric definitions, run the data-science-reviewer
   agent (from v2-phase-gated-agent-workflow if available). This
   checks for:
   - **Calculation correctness:** Are formulas right? Do totals add
     up? Are percentages computed from the right base?
   - **Join integrity:** When combining data sources, are rows being
     duplicated or dropped silently?
   - **Aggregation logic:** Are group-by operations using the right
     level? Could a SUM be double-counting?
   - **Metric definitions:** Are metrics defined consistently
     everywhere they appear? Does "revenue" mean the same thing in
     the summary and the detail view?
   - **Chart-data alignment:** Do visualizations actually show what
     their titles and labels claim?
   - **Edge cases:** What happens with nulls, zeros, empty groups,
     or negative values?

   Skip this review if the project has no data, math, or analysis
   components. Not every project needs it — but any project that
   produces numbers or charts does.

If any skill is not available (not installed or not applicable
to this project type), skip it and note in the findings that a
deeper review wasn't run. Don't let a missing skill block the
rest of the improvement pass.

Incorporate all findings from these reviews into Step 4 alongside
the manual audit findings and the user's concerns from Step 2.

## Step 4: Present findings

Organize everything — the user's concerns from Step 2 AND the audit
findings from Step 3 — into three priority levels:

### CRITICAL — should fix (blocks progress or has real problems)
- Things that are broken, buggy, or will cause pain soon
- Security issues (exposed secrets, missing input validation)
- Can't-run-the-project problems (missing setup docs, broken deps)

### IMPORTANT — worth improving (quality and maintainability)
- Template files that were never filled in
- Missing tests for important logic
- Stale workflow files that no longer reflect reality
- Code that works but is confusing or fragile

### NICE TO HAVE — polish (organization and style)
- Renaming or reorganizing files
- Minor cleanup
- Style consistency

For each finding:
- One sentence: what's wrong.
- One sentence: what fixing it would look like.
- No jargon. Explain why it matters, not just that it's "wrong."

After presenting, check the mode:

**If audit-only mode:** Skip to Step 7 to log the audit. Before
logging, ask:

> "That's the audit. No fixes today — this is just the health check.
> Anything here surprise you or that you want to flag for next time?"

Then tell the user when the next audit is due (see frequency guide
in Step 7).

**If full improve mode:** Ask:

> "Which of these do you want to tackle? You can pick specific items,
> a whole priority level, or tell me what order you'd prefer. We
> don't have to do everything today."

## Step 5: Create improvement arc in PLAN.md

Based on what the user chose, create a new arc in PLAN.md:

**Goal:** "Improvement pass: [summary of what we're fixing]"

**Why this arc, why now:** "Project improvement review on [date].
User concerns: [brief summary]. Audit found: [brief summary]."

**Tasks:** List specific, actionable items from the user's selection.
Each task should be completable in one sitting.

**Out of scope:** List the findings the user chose NOT to tackle, so
they're captured but won't creep in.

**Definition of done:** Specific conditions that prove each item is
actually fixed — not "code is cleaner" but "all functions in utils.py
have descriptive names" or "README has setup instructions that work
from a fresh clone."

If the project has no PLAN.md, write the improvement plan directly
to HANDOFF.md instead, or create a PLAN.md if the user wants one.

## Step 6: Execute improvements

Work through the plan items. For each one:

1. Show the user what you're about to change and why.
2. Make the change.
3. Verify it works (run tests, check output, etc.).
4. Confirm with the user before moving to the next item.

After each completed item, suggest running /log to capture it.

If something turns out to be bigger than expected, flag it:
> "This is bigger than it looked — it'll probably take [estimate].
> Want to keep going, or defer it and move to the next item?"

Do not rush through everything. One item done well beats five items
half-done.

After all improvements are complete, if the project has any UI or
browser-visible output, suggest:
> "Want to run /qa to test these changes in a browser before we
> wrap up?"

## Step 7: Log the audit/improvement

Whether this was audit-only or a full improvement pass, add an entry
to the **Improvement History** section at the bottom of PLAN.md:

For **audit-only** mode:
```
### [YYYY-MM-DD] — Audit (health check only)
- **Findings:** [count] critical, [count] important, [count] nice-to-have
- **Top concerns:** [1-3 sentence summary of the most important findings]
- **Action taken:** Audit only — no fixes this session
- **Next review:** [date, based on frequency guide below]
```

For **full improve** mode:
```
### [YYYY-MM-DD] — Improvement pass
- **Trigger:** [user-initiated / scheduled review]
- **What was reviewed:** [code, workflow files, tests, etc.]
- **What was fixed:** [list of changes actually made]
- **Deferred:** [anything identified but not fixed, and why]
- **Next review:** [date, based on frequency guide below]
```

### Audit frequency guide

Use this to suggest the next review date. Check the Improvement
History to see when the last audit was — if the project is overdue,
mention it at the start of the session.

| Project state | How to tell | Audit every |
|---|---|---|
| **Active** — working on it regularly | Commits in the last 2 weeks | 2-4 weeks |
| **Stable** — shipped, not changing | No commits in 30+ days | 90 days |
| **Just shipped** — big feature or release landed | Recent tag or milestone | Right after shipping |
| **Inherited/new-to-you** — picked up from someone else | First time running /improve | Immediately, then follow active/stable schedule |

When suggesting the next review date, pick a specific date (not
"in 30 days") so it's concrete and trackable. For example:
"Next review: 2026-06-15" not "Next review: ~30 days."

Then suggest running /wrap to close the session.

## Rules

- Do not change code without showing the user what you're changing
  and why. They're learning — every change is a teaching moment.
- Do not refactor working code just because it could be "cleaner"
  unless the user specifically asked for it.
- If the project has no tests, don't try to add 100% coverage. Pick
  the 2-3 most critical things and test those.
- If workflow files are empty templates, filling them in IS an
  improvement and should be offered as an early win.
- Be honest about what you find. Don't manufacture problems to seem
  thorough, and don't downplay real issues to be polite.
- Explain findings in plain language. If you say "this function has
  high cyclomatic complexity," also say what that means: "this
  function has too many if/else branches, which makes it hard to
  follow and easy to break."
- The user's concerns from Step 2 get equal weight with audit
  findings. If they say "the login page bugs me," that's a real
  finding even if the code is technically fine.
- Do not push to remote. Local changes only.
