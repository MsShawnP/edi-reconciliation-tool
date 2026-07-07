---
description: Initialize a new project with the solo dev workflow structure. Run from the project directory.
---

Set up a new project with the full workflow structure. Do these in
order.

Argument: $ARGUMENTS
- $ARGUMENTS should contain two things, separated by a pipe:
  PROJECT_NAME | BUSINESS_QUESTION
- Example: "Trade Spend Diagnostic | For a $25M specialty food brand,
  where is the trade spend going and what's the addressable improvement?"
- If $ARGUMENTS is empty, ask for the project name and business
  question before proceeding.

## Step 1: Verify prerequisites

1. Confirm we're in a git repo (`git rev-parse --is-inside-work-tree`).
   If not, ask the user: initialize one here, or are we in the wrong
   directory?
2. Check if the workflow-package repo is cloned locally. Look in these
   locations in order:
   - `~/projects/reference/claude-solo-dev-workflow/workflow-package/` (Mac/Linux)
   - `%USERPROFILE%\projects\reference\claude-solo-dev-workflow\workflow-package\` (Windows)
   - `~/claude-solo-dev-workflow/workflow-package/` (Mac/Linux) or `%USERPROFILE%\claude-solo-dev-workflow\workflow-package\` (Windows)
   If not found, clone it to a temporary location:
   - Mac/Linux: `git clone https://github.com/MsShawnP/claude-solo-dev-workflow.git /tmp/claude-solo-dev-workflow`
   - Windows: `git clone https://github.com/MsShawnP/claude-solo-dev-workflow.git "$env:TEMP\claude-solo-dev-workflow"`
   and use the `workflow-package/` directory within as the source.
3. Check if any workflow files already exist (CLAUDE.md, PLAN.md,
   HANDOFF.md, DECISIONS.md, FAILURES.md, .claude/commands/). If
   they do, stop and report what's already there. Do not overwrite
   without explicit confirmation.

## Step 2: Create directory structure

```
.claude/
  commands/
```

## Step 3: Copy and fill templates

Copy these files from the workflow-package `templates/` directory into
the project root:

- CLAUDE.md
- DECISIONS.md
- HANDOFF.md
- PLAN.md
- FAILURES.md

In every copied file, replace `[PROJECT NAME]` with the PROJECT_NAME
from $ARGUMENTS.

In CLAUDE.md, replace `[One sentence. If you can't write this sentence
cleanly, the project isn't scoped enough yet.]` with the
BUSINESS_QUESTION from $ARGUMENTS.

Leave all other bracketed sections as-is — they get filled in during
the 95% confidence conversation or as the project develops.

## Step 4: Copy slash commands

Copy from the workflow-package `slash-commands/` directory:

- `log.md` → `.claude/commands/log.md`
- `wrap.md` → `.claude/commands/wrap.md`
- `improve.md` → `.claude/commands/improve.md`
- `commands.md` → `.claude/commands/commands.md`
- `pre-ship.md` → `.claude/commands/pre-ship.md`

Also copy this file (`init.md`) into `.claude/commands/init.md` so
future projects can be initialized the same way.

## Step 5: Create .gitignore (if one doesn't exist)

If no .gitignore exists, create one with sensible defaults:

```
# Rendered output
*.html
_freeze/
_site/

# R
.Rproj.user/
.Rhistory
.RData
.Rdata
renv/library/

# Python
__pycache__/
*.pyc
.venv/
venv/

# Environment and secrets
.env
*.env

# Data files (uncomment if needed)
# *.db
# *.sqlite
# data/raw/

# OS
.DS_Store
Thumbs.db
```

If a .gitignore already exists, skip this step — do not modify it.

## Step 6: Initial commit

1. `git add -A`
2. `git commit -m "chore: initialize project with solo dev workflow"`
3. Report the commit hash and file list.

Do not push. Do not create tags — the user decides when to tag.

## Step 7: Report

After setup is complete, print:

```
Project initialized: [PROJECT_NAME]

Files created:
  CLAUDE.md          — project rules and context
  DECISIONS.md       — durable choices log
  HANDOFF.md         — session state log
  PLAN.md            — current work arc
  FAILURES.md        — things that didn't work
  .claude/commands/
    log.md           — /log: save a checkpoint
    wrap.md          — /wrap: end-of-session protocol
    improve.md       — /improve: review and improve the project
    commands.md      — /commands: show all available commands
    init.md          — /init: this command
```

Then print the next steps guide below. This is the most important
part — the user may be new to development, so be explicit about
what each step is, why it matters, and exactly what to do.

```
---------------------------------------------------
WHAT TO DO NEXT (in order)
---------------------------------------------------

STEP 1: Fill in CLAUDE.md (do this now, takes 5 minutes)

  Open CLAUDE.md and fill in the bracketed sections:
  - "What this project is" — write one paragraph about what
    you're building and who it's for
  - "Stack and tools" — what language, what libraries, what
    database (if any)
  - "Voice and standards" — how should written output sound?
    (the default is fine to start with)

  WHY: This is the file Claude reads at the start of every
  session. The more specific it is, the better Claude
  understands your project. A vague CLAUDE.md means Claude
  will ask you the same questions every time.

STEP 2: Write your first plan in PLAN.md (do this now)

  Open PLAN.md and fill in:
  - Goal: what does "done" look like for your first chunk of
    work? Keep it small — something you could finish in 1-3
    sessions.
  - Tasks: break the goal into specific steps. Each one
    should be something you could finish in one sitting.
  - Definition of done: how will you know it's actually done?
    Not "it works" — what specifically works?

  WHY: Without a plan, sessions drift. The plan keeps both
  you and Claude focused on the same goal.

STEP 3: Challenge the idea (recommended, takes 10 min)

  Before you start building, stress-test the idea:

  /office-hours   — A critical-friend conversation that pokes
                    holes in your concept. Finds problems now,
                    not after you've built the wrong thing.

  /plan-ceo-review — Product gate. Checks: is this the right
                    thing to build? Is the scope right? Does
                    the plan make a clear case for why it
                    matters?

  /plan-eng-review — Architecture gate. Checks: will the
                    technical approach actually work? What's
                    going to break? What's missing?

  WHY: These take 10 minutes total and can save you days of
  building something that doesn't hold up. You can skip them
  for quick/throwaway projects, but for anything you'll
  maintain, they're worth it.

STEP 4: Start building (you're ready)

  You can start coding now. As you work:

  - Run /log after each meaningful change (bug fixed,
    feature added, decision made). This saves a checkpoint
    you can come back to.
  - Run /wrap when you're done for the day. This captures
    everything that happened so your next session can pick
    up where you left off.
  - Run /improve anytime you want to step back and make the
    project better — it audits your code and workflow files,
    then walks you through fixing what matters.
  - Run /qa after building a feature to test it in a real
    browser and catch things that look wrong.

---------------------------------------------------
OPTIONAL: More skills you can use anytime
---------------------------------------------------

  /clarify    — Claude interviews you until it's 95% sure
                what you actually want. Great when you have
                a fuzzy idea but aren't sure how to scope it.

  /ce:brainstorm — Explore what to build through back-and-
                forth conversation. Good before you commit
                to an approach.

  /ce:plan    — Creates a detailed implementation plan with
                research. Use after you know WHAT to build
                but want help figuring out HOW.

  /ce:work    — Executes a plan efficiently. Use when you
                have a plan and want to get it done.

  /ce:review  — Multi-reviewer code review. Run before you
                consider something done.

  /commands   — Quick reference card with all commands.

You don't need to use all of these. Start with /log and
/wrap — they're the foundation. Add others when they'd help.
---------------------------------------------------
```

## Rules

- Do not modify any existing files without asking.
- Do not push to remote.
- If any step fails, stop and report. Do not attempt to fix
  automatically.
- This command is idempotent for the check step — running it on an
  already-initialized project should report what exists and stop,
  not duplicate anything.
