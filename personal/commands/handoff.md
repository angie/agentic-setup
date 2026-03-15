# Session Handoff

Generate a structured handoff document so the next session (in any agent) can resume seamlessly.

**Format defined in:** @~/projects/agent-config/core/handoff-schema.md

## Process

1. **Gather state** by running these commands:

```bash
git status -sb
git log --oneline -5
git branch --show-current
```

2. **Check for an open PR** on the current branch:

```bash
gh pr view --json number,title,url,state 2>/dev/null || echo "No PR"
```

3. **Run checks** (if a test/lint/typecheck script exists):

```bash
npm test --timing=false 2>&1 | tail -20
npx tsc --noEmit 2>&1 | tail -10
npm run lint --timing=false 2>&1 | tail -10
```

4. **Produce `HANDOFF.md`** in the project root using the canonical schema from core/handoff-schema.md. Fill in every section based on the gathered state and the work done in this session.

5. **Tell the user:**

> Handoff saved to `HANDOFF.md`. In your next session, run `/pickup` to resume.
