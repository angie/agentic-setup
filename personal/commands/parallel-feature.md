# Parallel Feature Orchestration

Orchestrate a complex feature across multiple parallel workstreams, with support for split-repo patterns (ops repo for orchestration, code repo for implementation).

**Usage**: `/parallel-feature [PRD_PATH_OR_DESCRIPTION]`

**Argument**: Path to PRD file (e.g., `.taskmaster/docs/prd.md`) or inline feature description

---

## Phase 0: Detect Project Structure

First, check for split-repo configuration:

```bash
# Check for project.json in current directory
cat project.json 2>/dev/null || echo "No project.json found - using single-repo mode"
```

### Split-Repo Mode (if project.json exists)
- **Ops repo** (current): Task Master, PRDs, agent briefings, workstream tracking
- **Code repo** (from config): All code, branches, worktrees, PRs
- Worktrees created in separate directory to keep both repos clean

### Single-Repo Mode (default)
- Everything in one repository
- Standard worktree pattern

**Store the config for use throughout:**
```javascript
// Parse project.json if exists
const config = {
  splitRepo: true/false,
  opsPath: '.',
  codePath: '../garden',           // from project.json
  worktreesPath: '../garden-worktrees',
  github: { owner: 'angie', codeRepo: 'garden' }
};
```

---

## Phase 1: Parse & Analyse

Run Task Master in the **ops repo** (current directory):

### If PRD file provided:
```bash
task-master parse-prd $ARGUMENTS --research
```

### If inline description:
Create a PRD file at `.taskmaster/docs/[feature-name].md`, then parse it.

### Then analyse:
```bash
task-master analyze-complexity --research
task-master expand --all --research
task-master list --with-subtasks
```

**Output required**:
- Total tasks and subtasks
- Complexity scores
- Dependency map

---

## Phase 2: Identify Workstreams

Analyse the tasks to identify parallel-safe workstreams. Group by:

1. **Layer** (DB, API, UI, Tests)
2. **Feature slice** (if vertical slicing makes sense)
3. **Concern** (auth, payments, notifications)

### Criteria for parallel-safe:
- No shared file modifications
- Clear dependency boundaries
- Can be merged independently

### Output format:
```markdown
## Proposed Workstreams

| Workstream | Tasks | Dependencies | Est. Complexity |
|------------|-------|--------------|-----------------|
| [name] | 1.1, 1.2, 1.3 | None | Medium |
| [name] | 2.1, 2.2 | Workstream 1 | High |

### Dependency Graph
[ASCII diagram showing order]
```

**Ask user**: "Does this workstream breakdown look right? Any adjustments?"

---

## Phase 3: Setup Infrastructure

Once user approves workstreams:

### 3.1 Create GitHub tracking issue (in CODE repo)

```bash
# Switch to code repo for GitHub operations
cd [CODE_REPO_PATH]

gh issue create \
  --title "Feature: [FEATURE_NAME]" \
  --label "parallel-feature" \
  --body "$(cat <<'EOF'
## Feature Overview
[From PRD summary]

## Workstreams
- [ ] Workstream 1: [name] - #TBD
- [ ] Workstream 2: [name] - #TBD
- [ ] Workstream 3: [name] - #TBD

## Progress Tracking
Updated by conductor agent.

## Task Master Reference
Tasks tracked in: [ops-repo-url] (garden-ops)

## Merge Order
1. [first workstream]
2. [second workstream]
3. [third workstream]
EOF
)"

# Return to ops repo
cd [OPS_REPO_PATH]
```

### 3.2 Create branches and worktrees (in CODE repo)

**For split-repo mode:**
```bash
# Create worktrees directory if needed
mkdir -p [WORKTREES_PATH]

# Create branches in code repo
cd [CODE_REPO_PATH]
git branch feature/[feature]-[workstream]

# Create worktrees in separate location (keeps code repo clean)
git worktree add [WORKTREES_PATH]/[feature]-[workstream] feature/[feature]-[workstream]

cd [OPS_REPO_PATH]
```

**For single-repo mode:**
```bash
git branch feature/[feature]-[workstream]
git worktree add ../[project]-[workstream] feature/[feature]-[workstream]
```

### 3.3 Create Task Master tags (in OPS repo)

```bash
task-master add-tag --name=ws-[workstream] --description="[Workstream description]"
task-master move --from=[task-ids] --toTag=ws-[workstream]
```

### 3.4 Create workstream tracking issues (in CODE repo)

For each workstream:
```bash
cd [CODE_REPO_PATH]

gh issue create \
  --title "Workstream: [NAME]" \
  --label "parallel-feature,workstream:[name]" \
  --body "$(cat <<'EOF'
## Parent Feature
Relates to #[parent-issue]

## Tasks
Tracked in garden-ops: `task-master list --tag=ws-[workstream]`

## Dependencies
- Blocked by: [workstreams]
- Blocks: [workstreams]

## Completion Criteria
- [ ] All tasks done in Task Master
- [ ] Tests passing
- [ ] PR approved
EOF
)"

cd [OPS_REPO_PATH]
```

---

## Phase 4: Generate Agent Instructions

Create briefing files in the **OPS repo** at `./workstreams/`:

```bash
mkdir -p ./workstreams
```

**File**: `./workstreams/[feature]-[workstream].md`

```markdown
# Workstream: [NAME]

## Project Structure
This project uses a split-repo pattern:
- **Ops repo** (garden-ops): Task Master, PRDs, this briefing
- **Code repo** (garden): Your working directory for all code
- **Your worktree**: [WORKTREES_PATH]/[feature]-[workstream]

## Quick Reference
- **Branch**: feature/[feature]-[workstream]
- **Worktree**: [WORKTREES_PATH]/[feature]-[workstream]
- **Task Master Tag**: ws-[workstream]
- **Tracking Issue**: [CODE_REPO]#[number]
- **Parent Feature**: [CODE_REPO]#[parent-number]

## Your Mission
[Specific goal for this workstream]

## Getting Your Tasks
From the ops repo (garden-ops), run:
```bash
cd [OPS_REPO_PATH]
task-master list --tag=ws-[workstream]
task-master show [task-id]
```

Or reference the Task Master MCP tools.

## Dependencies
### Waiting On
- [List any blocking workstreams]

### Your Deliverables (others depend on)
- [List what you produce that others need]

## Shared Integration Points
- Types: `src/types/[feature].ts`
- Contracts: `src/api/[feature]/types.ts`

## Working Protocol
1. **Start session** (in your worktree):
   ```bash
   cd [WORKTREES_PATH]/[feature]-[workstream]
   ```

2. **Get next task** (reference ops repo):
   ```bash
   cd [OPS_REPO_PATH] && task-master next --tag=ws-[workstream]
   ```

3. **Before coding**: Write failing test (TDD!)

4. **After each subtask**:
   ```bash
   # In ops repo - update task status
   cd [OPS_REPO_PATH]
   task-master set-status --id=[id] --status=done

   # In your worktree - commit and push
   cd [WORKTREES_PATH]/[feature]-[workstream]
   git add . && git commit -m "feat: [description]"
   git push origin feature/[feature]-[workstream]
   ```

5. **On blocker**: Comment on tracking issue #[number]

6. **On completion**: Create PR in code repo, update tracking issue

## PR Creation
```bash
cd [WORKTREES_PATH]/[feature]-[workstream]
gh pr create \
  --title "Workstream: [NAME]" \
  --label "parallel-feature,workstream:[name]" \
  --body "Parent Feature: #[parent]
Workstream Tracking: #[tracking]
blocked-by:#[if-any]

## Summary
[What this delivers]

## Task Master Tasks
Completed: [list task IDs]"
```

## Communication
- Push frequently (every completed subtask minimum)
- Update tracking issue with progress
- Tag conductor on blockers
```

---

## Phase 5: Launch Instructions

Output the launch commands:

```markdown
## Ready to Launch!

### Project Structure
- **Ops repo**: [OPS_REPO_PATH] (Task Master lives here)
- **Code repo**: [CODE_REPO_PATH] (PRs and branches here)
- **Worktrees**: [WORKTREES_PATH]/ (agents work here)

### Terminal Setup

**Terminal 0 - Conductor (ops repo):**
```bash
cd [OPS_REPO_PATH]
# This terminal for monitoring and Task Master operations
```

**Terminal 1 - [Workstream 1]:**
```bash
cd [WORKTREES_PATH]/[feature]-[workstream1] && claude
```
Then: "You are the [workstream1] agent. Read [OPS_REPO_PATH]/workstreams/[feature]-[workstream1].md for your instructions."

**Terminal 2 - [Workstream 2]:**
```bash
cd [WORKTREES_PATH]/[feature]-[workstream2] && claude
```
Then: "You are the [workstream2] agent. Read [OPS_REPO_PATH]/workstreams/[feature]-[workstream2].md for your instructions."

[Repeat for each workstream]

### Conductor Dashboard

Monitor progress from ops repo:
```bash
cd [OPS_REPO_PATH]

# Task progress
task-master list --status=in-progress
task-master list --status=done

# GitHub status (in code repo)
cd [CODE_REPO_PATH]
gh pr list --label "parallel-feature"
gh issue list --label "parallel-feature"
```

### Merge Order
When workstreams complete, merge PRs in code repo in this order:
1. [first] - No dependencies
2. [second] - After [first] merged
3. [third] - After [second] merged
```

---

## Phase 6: Cleanup (after feature complete)

```bash
# Remove worktrees (from code repo)
cd [CODE_REPO_PATH]
git worktree remove [WORKTREES_PATH]/[feature]-[workstream1]
git worktree remove [WORKTREES_PATH]/[feature]-[workstream2]

# Delete merged branches
git branch -d feature/[feature]-[workstream1]
git branch -d feature/[feature]-[workstream2]

# Archive Task Master tags (in ops repo)
cd [OPS_REPO_PATH]
task-master delete-tag --name=ws-[workstream1]
task-master delete-tag --name=ws-[workstream2]

# Archive workstream briefings
mkdir -p ./workstreams/archive
mv ./workstreams/[feature]-*.md ./workstreams/archive/

# Close tracking issues (in code repo)
cd [CODE_REPO_PATH]
gh issue close [parent] --comment "Feature complete!"

# Prune
git worktree prune
git fetch --prune
```

---

## Path Reference (Split-Repo)

For garden project:
- `[OPS_REPO_PATH]` = `/Users/angie/projects/personal/digital-garden-project/garden-ops`
- `[CODE_REPO_PATH]` = `/Users/angie/projects/personal/digital-garden-project/garden`
- `[WORKTREES_PATH]` = `/Users/angie/projects/personal/digital-garden-project/garden-worktrees`

---

## Error Handling

### If workstream gets blocked:
1. Check dependency workstream progress
2. If blocker is a shared type/contract, extract to separate PR and merge first
3. If fundamental issue, pause and reassess workstream split

### If merge conflicts:
1. Rebase workstream branch on main
2. Resolve conflicts
3. Re-run tests
4. Force push (with care) or create fixup commit

### If tests fail after merge:
1. Check integration points
2. May need coordination commit across workstreams
3. Consider feature flag to merge incrementally

### If Task Master and code get out of sync:
1. Task status is source of truth for "what's done"
2. Code repo commits are source of truth for "what's implemented"
3. Reconcile by checking both before marking complete
