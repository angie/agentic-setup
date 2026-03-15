# Setup Parallel Feature Workflows

Set up GitHub Actions and labels for parallel feature development in the current repository.

**Usage**: `/setup-parallel-workflows`

---

## Step 1: Create GitHub Labels

```bash
# Create workstream tracking labels
gh label create "parallel-feature" --color "6f42c1" --description "Part of a parallel feature development"
gh label create "auto-merge" --color "0e8a16" --description "Eligible for automatic merging when conditions met"
gh label create "workstream:db" --color "1d76db" --description "Database layer workstream"
gh label create "workstream:api" --color "0e8a16" --description "API layer workstream"
gh label create "workstream:ui" --color "d93f0b" --description "UI layer workstream"
gh label create "workstream:tests" --color "fbca04" --description "Test suite workstream"
gh label create "blocker" --color "b60205" --description "Blocking other work"
```

---

## Step 2: Create GitHub Actions Workflow

Create the auto-merge workflow:

```bash
mkdir -p .github/workflows
```

Then copy the workflow from `~/.claude/templates/github-actions/auto-merge-workstreams.yml`:

```bash
cp ~/.claude/templates/github-actions/auto-merge-workstreams.yml .github/workflows/
```

---

## Step 3: Configure Repository Settings

**Manual steps required in GitHub UI:**

1. Go to **Settings → General → Pull Requests**
   - ✅ Enable "Allow auto-merge"
   - ✅ Enable "Automatically delete head branches"

2. Go to **Settings → Branches → Add rule** for `main`:
   - ✅ Require a pull request before merging
   - ✅ Require approvals (1 minimum)
   - ✅ Require status checks to pass
   - ✅ Require branches to be up to date
   - Select your CI checks as required

3. Go to **Settings → Actions → General**:
   - Workflow permissions: "Read and write permissions"
   - ✅ Allow GitHub Actions to create and approve pull requests

---

## Step 4: Create PR Template

Create `.github/PULL_REQUEST_TEMPLATE/workstream.md`:

```markdown
## Workstream PR

**Parent Feature**: #
**Task Master Tasks**:

## Summary


## Dependencies
- [ ] Blocked by: # (leave empty if none)
- [ ] Blocks: # (leave empty if none)

## Changes


## Testing
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project conventions
- [ ] Tests added/updated
- [ ] Documentation updated (if applicable)
- [ ] Ready for auto-merge (add `auto-merge` label when ready)
```

---

## Step 5: Verify Setup

```bash
# Check labels exist
gh label list | grep -E "(parallel-feature|auto-merge|workstream)"

# Check workflow exists
ls -la .github/workflows/auto-merge-workstreams.yml

# Test workflow syntax
gh workflow view auto-merge-workstreams.yml
```

---

## Usage Guide

### Creating a Workstream PR

1. Create PR from workstream branch
2. Add labels: `parallel-feature`, `workstream:[type]`
3. Fill in the PR template, noting dependencies
4. Get review and approval
5. Add `auto-merge` label when ready
6. Workflow handles merging in correct order

### Dependency Syntax

In PR body, use:
```
blocked-by:#123
```

The workflow will wait until PR #123 is merged before auto-merging.

### Monitoring

```bash
# Watch workflow runs
gh run list --workflow=auto-merge-workstreams.yml

# Check specific run
gh run view [run-id]
```

---

## Troubleshooting

### PR not auto-merging?

Check:
1. Has `auto-merge` label?
2. Has `parallel-feature` label?
3. Has at least one approval?
4. All CI checks passing?
5. No merge conflicts?
6. All `blocked-by` PRs merged?

### Workflow not triggering?

Check:
1. Workflow file in `.github/workflows/`
2. Actions enabled in repo settings
3. Workflow has correct permissions
