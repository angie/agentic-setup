# Fix Issue

End-to-end issue resolution following TDD workflow.

**Input:** $ARGUMENTS (GitHub issue number or URL)

If no issue is provided, ask the user for one.

**Core workflow:** @~/projects/agent-config/core/workflow.md
**Quality gates:** @~/projects/agent-config/core/gates.md

## Process

### 1. Understand the Issue

```bash
gh issue view $ARGUMENTS --json title,body,labels,assignees,comments
```

Read the issue thoroughly. Identify:
- What behaviour needs to change or be added
- Acceptance criteria (explicit or implied)
- Affected files or areas of the codebase

### 2. Create a Branch

```bash
gh issue develop $ARGUMENTS --checkout 2>/dev/null || git checkout -b fix/$ARGUMENTS
```

### 3. TDD Cycle

Follow RED-GREEN-REFACTOR strictly:

**RED:**
- Write a failing test that describes the expected behaviour from the issue
- Run the test to confirm it fails for the right reason

**GREEN:**
- Write the minimum code to make the test pass
- Run all tests to confirm nothing is broken

**REFACTOR:**
- Assess the code for improvement opportunities
- Only refactor if it adds clear value
- Run all tests after refactoring

Repeat the cycle for each behaviour described in the issue.

### 4. Run Quality Gates

Before committing, verify all gates pass:

```bash
npm test --timing=false
npx tsc --noEmit
npm run lint --timing=false 2>/dev/null || npx biome check .
```

### 5. Commit

Use `committer` if available, otherwise commit directly. Include the issue reference:

```bash
committer -m "fix: <description>

Closes #$ARGUMENTS" <files...>
```

### 6. Push and Create PR

```bash
git push -u origin HEAD
gh pr create --title "fix: <description>" --body "$(cat <<'EOF'
## Summary

- [What was fixed and why]

## Test Plan

- [How the fix is verified]

Closes #$ARGUMENTS
EOF
)"
```

### 7. Close the Issue

The PR's `Closes #N` reference will close the issue automatically on merge. If immediate closure is needed:

```bash
gh issue close $ARGUMENTS --comment "Fixed in PR #<number>"
```

Report the PR URL to the user when done.
