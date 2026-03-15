# Attack (Breaker)

Run the Breaker step of adversarial pairing.

**Protocol:** @~/projects/agent-config/core/adversarial-pairing.md

## Input

`$ARGUMENTS` should include:
- Original goal
- Builder proposal (or a reference to it)

If proposal text is missing, ask for it.

## Process

1. Identify top 5 concrete breakages.
2. Include at least:
   - 2 edge cases
   - 1 regression risk
   - 1 operability/rollback concern
3. Provide evidence for each claim (file/line, command, test behaviour, or reproducible path).
4. Mark each finding severity: Critical / High / Medium / Low.
5. Suggest minimal mitigations for valid findings.

## Output Format

- Breakage Findings (ordered by severity)
- Evidence
- Minimal Mitigations
- Revised Risk Profile
- Breaker Scorecard (impact across rubric categories)
- Next step: "Run /judge with Builder+Breaker outputs."
