---
description: Show available workflow commands and when to use each one
---

Print this quick reference card. No arguments needed.

```
---------------------------------------------------
WORKFLOW COMMANDS — quick reference
---------------------------------------------------

Type / in the chat to see all available commands.
These are the workflow commands and when to use them:

DURING SETUP
  /init          Set up a new project with all workflow files.
                 Use once, at the very beginning.

  /add-workflow  Add workflow files to a project that already
                 exists. Use when you have code but no PLAN.md,
                 HANDOFF.md, etc.

BEFORE BUILDING (challenge the idea first)
  /office-hours  Critical-friend conversation. Pokes holes in
                 your idea so you find problems before building.

  /plan-ceo-review  Product gate. Is this the right thing to
                 build? Is the scope right? Does it matter?

  /plan-eng-review  Architecture gate. Will the technical
                 approach work? What's going to break?

WHILE WORKING
  /log           Save a checkpoint. Run after each meaningful
                 change — bug fixed, feature added, decision
                 made. Quick, takes 10 seconds.

  /improve       Review and improve the project. Audits your
                 code, tests, security, and workflow files,
                 then walks you through fixing what matters.
                 Also: /improve audit-only (health check only).

  /qa            Test the project in a real browser. Checks
                 that things actually work, not just compile.
                 Run after building or fixing something.

  /pre-ship      Pre-ship checklist. Verifies: runs from a
                 fresh clone, no hardcoded secrets, deps
                 pinned, README has setup instructions, work
                 is pushed to a remote. Run before shipping.

WHEN STOPPING
  /wrap          End-of-session protocol. Captures everything
                 that happened so your next session picks up
                 right where you left off.

ANYTIME
  /commands      This card. Shows what's available.

---------------------------------------------------
FULL WORKFLOW ORDER — new projects
---------------------------------------------------

Phase 1 — Build the right thing
   1. /clarify            Interview until the idea is clear
   2. /office-hours       Challenge the idea, find problems
   3. /plan-ceo-review    Product check: worth building?
   4. /plan-eng-review    Technical check: will it work?

Phase 2 — Build it right
   5. /init               Scaffold project files
   6. /ce:brainstorm      Spec out the approach
   7. /ce:plan            Detailed implementation plan
   8. /ce:work            Execute the plan
   9. /ce:review          Multi-reviewer code review
  10. /qa                 Test it in a browser

Phase 3 — Finish and learn
  11. /pre-ship           Verify it works from scratch, no secrets
  12. /ce:compound        Capture learnings for future sessions
  13. Ship

While working, repeat as needed:
      /log               After each meaningful change
      /wrap              When done for the day

---------------------------------------------------
FULL WORKFLOW ORDER — improving existing projects
---------------------------------------------------

   1. /improve            Audit + fix (or /improve audit-only)
   2. /qa                 Test the fixes in a browser
   3. /wrap               End the session

---------------------------------------------------
TIER SHORTCUT — you don't always need all 12 steps
---------------------------------------------------

  Quick  (throwaway, < 1 day)
         /clarify only, then build

  Medium (feature, weekend project)
         Skip steps 2-4. Start at /clarify, then
         /init → /ce:brainstorm → /ce:plan → build.

  Heavy  (product, maintained > 3 months)
         All 12 steps.

---------------------------------------------------
TIP: Type / and you'll see a list of all commands.
     Arrow-key to the one you want and hit Enter.
---------------------------------------------------
```

After printing the card, add a one-line suggestion based on the
current project state:

- If PLAN.md has no active tasks → "You might want to start with
  /improve to see what needs work."
- If HANDOFF.md's last entry is old → "Looks like it's been a while.
  Try /improve audit-only for a quick health check."
- If there are uncommitted changes → "You have uncommitted changes.
  Run /log to save a checkpoint."
- If none of the above apply → "You're in good shape. Keep working
  and run /log when you finish something."
