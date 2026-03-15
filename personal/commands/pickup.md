# Session Pickup

Resume work from a previous session's handoff document. Works regardless of which agent produced the handoff.

**Format defined in:** @~/projects/agent-config/core/handoff-schema.md

## Process

1. **Read project configuration:**
   - Read the project's `CLAUDE.md` (if it exists)
   - Read any referenced core or adapter files

2. **Read `HANDOFF.md`** from the project root. If it does not exist, tell the user:
   > No HANDOFF.md found in this project. Use `/handoff` at the end of a session to create one.

3. **Verify working tree** matches the handoff:

```bash
git status -sb
git branch --show-current
```

   If the working tree differs from what HANDOFF.md describes, flag the discrepancies before proceeding.

4. **Check CI/PR state** if a PR is mentioned:

```bash
gh pr view --json number,title,state,statusCheckRollup 2>/dev/null
```

5. **Summarise the state** for the user:
   - What was being worked on
   - Current TDD phase (RED/GREEN/REFACTOR)
   - What was accomplished
   - What the next steps are
   - Any risks or gotchas to be aware of

6. **Propose 2-3 actions** based on the Next Steps section. Ask the user which to start with.

7. **Offer cleanup:**
   > Shall I remove HANDOFF.md now that we've picked up the context?
