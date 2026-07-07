---
description: Pre-ship checklist — verify the project works from scratch, secrets are excluded, and it's ready to share before shipping.
---

Run this before shipping, sharing, deploying, or calling something
"done." It catches the things that work on your machine but break
everywhere else.

Run this AFTER /ce:review and /qa, BEFORE shipping or /ce:compound.

Argument: $ARGUMENTS
- If $ARGUMENTS is provided, treat it as context for what kind of
  shipping (e.g., "deploying to production" vs "sharing with a friend"
  vs "submitting for class").
- If $ARGUMENTS is empty, run the full checklist.

## Step 1: Can it run from scratch?

Check whether someone (or you on a new machine) could clone this
project and get it running without asking questions:

### 1a. Dependencies declared
- Look for dependency files: package.json, requirements.txt,
  Pipfile, renv.lock, Gemfile, go.mod, Cargo.toml, etc.
- If none exist and the project uses external libraries, flag it:
  > "This project uses [libraries] but doesn't have a dependency
  > file. Anyone who clones this won't be able to run it."

### 1b. Lock file committed
- If there's a dependency file, check for a corresponding lock file
  (package-lock.json, poetry.lock, renv.lock, Gemfile.lock, etc.)
- If the lock file exists but isn't tracked by git, flag it:
  > "The lock file exists but isn't committed. This means different
  > people could get different dependency versions."

### 1c. Environment variables
- Check for .env files. If the project uses environment variables:
  - Is there a .env.example or .env.template with all required
    variables (values blanked out)?
  - Is .env in .gitignore? (It should be — never commit real secrets.)
  - Flag if .env exists but .env.example doesn't:
    > "You have a .env file but no .env.example. Someone cloning
    > this won't know what variables they need to set."

### 1d. README has setup instructions
- Does the README explain:
  - How to install dependencies?
  - How to configure environment variables?
  - How to run the project?
  - How to run tests (if they exist)?
- If the README is missing or doesn't cover these, flag it.

### 1e. Entry point works
- Try to identify and run the project's entry point. If it fails
  immediately, that's a blocker.

## Step 2: Are secrets excluded?

Search the codebase for things that should never be committed:

### 2a. Hardcoded secrets
- Search for patterns that look like API keys, tokens, passwords:
  - Strings that look like API keys (long alphanumeric strings)
  - Variables named password, secret, token, api_key, etc. that
    have hardcoded values (not environment variable references)
  - Connection strings with credentials embedded

### 2b. Sensitive files
- Check if any of these are tracked by git:
  - .env (with real values)
  - credentials.json, service-account.json
  - Private key files (.pem, .key)
  - Database files with real data (.sqlite, .db)

### 2c. Gitignore coverage
- Is .gitignore present and reasonable for the project type?
- Are common sensitive patterns covered?

## Step 3: Does it actually work end-to-end?

Beyond /qa's browser testing, check the full pipeline:

- If it's a data project: does the data load? Do the
  transformations run? Does the output generate?
- If it's a web app: does it start? Can you hit the main page?
  Do API endpoints respond?
- If it's a script/tool: does it run with expected input?
  Does it handle missing input gracefully?

### 3a. Tests
- If tests exist: do they all pass? Run them and report results.
- If no tests exist: flag it as a suggestion (not a blocker):
  > "This project has no tests. Tests catch bugs before your users
  > do. Consider adding at least one test for the main thing your
  > project does. You can ask Claude to help write them."
- Never block shipping solely because tests don't exist — but
  always mention it so the user is aware.

## Step 4: Is it pushed to a remote?

Check git remote status:
- Is a remote configured? (`git remote -v`)
- Are all commits pushed? (`git status` vs remote)
- If not pushed, warn:
  > "Your work only exists on this machine right now. If anything
  > happens to this computer, everything is lost. Push to a remote
  > (GitHub, etc.) to back it up."

## Step 5: Report

Present findings as a go/no-go checklist:

```
PRE-SHIP CHECKLIST — [date]

PASSED:
  [x] Dependencies declared and locked
  [x] No hardcoded secrets found
  [x] .gitignore covers sensitive files
  [x] Tests pass

FAILED:
  [ ] No .env.example (people won't know what vars to set)
  [ ] README missing setup instructions
  [ ] Not pushed to remote

VERDICT: [READY TO SHIP / FIX THESE FIRST]
```

If everything passed:
> "Looks ready to ship. Run /ce:compound to capture learnings,
> then you're done."

If there are failures:
> "Found [N] things to fix before shipping. Want to tackle them
> now? They're usually quick."

## Rules

- Don't block shipping over style issues. This checklist is about
  "will it work for someone else," not "is the code beautiful."
- Secrets are always a blocker. Never ship with exposed credentials.
- Be specific about what's wrong and how to fix it. "README needs
  work" is not useful. "README is missing: how to install deps,
  how to set env vars, how to run the project" is useful.
- If the project is genuinely just for the user (never sharing),
  scale the checklist down — skip README and .env.example checks,
  but still check for secrets and backup.
- Always end with what command to run next.
