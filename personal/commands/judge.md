# Judge

Run the Judge step of adversarial pairing.

**Protocol:** @~/projects/agent-config/core/adversarial-pairing.md

## Input

`$ARGUMENTS` should include:
- Original goal
- Builder output
- Breaker output

If either output is missing, ask for the missing artifact.

## Process

1. Score the Builder proposal and revised proposal using the 5-category rubric (0-10 each).
2. Decide:
   - Winner, or
   - Synthesised merged approach
3. Explain rubric deltas briefly with evidence.
4. Produce an ordered implementation checklist.
5. Provide verification commands and residual risks.
6. Apply stop rules from the protocol.

## Output Format

- Decision
- Rubric Table (A vs B)
- Why This Wins
- Implementation Checklist
- Verification Commands
- Residual Risks + Fallback
