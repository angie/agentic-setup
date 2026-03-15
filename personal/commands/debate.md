# Debate (Builder)

Run the Builder step of adversarial pairing.

**Protocol:** @~/projects/agent-config/core/adversarial-pairing.md

## Input

`$ARGUMENTS` = problem statement, issue URL, or desired outcome.

If no input is provided, ask for the target decision/problem.

## Process

1. Restate the goal in 1-2 lines.
2. Produce a minimal viable approach:
   - Target files
   - Proposed changes
   - Test changes (RED->GREEN->REFACTOR expectation)
   - Verification commands
3. State top 3 risks.
4. Provide a compact checklist for implementation.
5. End with: "Run /attack <same input> with this proposal to stress-test it."

## Output Format

- Goal
- Proposed Approach
- File Plan
- Test Plan
- Verification
- Risks
- Builder Scorecard (self-score 0-10 for each rubric category)
