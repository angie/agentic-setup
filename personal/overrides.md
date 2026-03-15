# Personal Overrides

> These rules are appended to the upstream CLAUDE.md and always take precedence.
> This file must never be overwritten by `sync`. It is the protected personal layer.

---

## Language

All commit messages, PR descriptions, code comments, and written communication must use **British English** (colour, behaviour, organised, favour, authorised, etc.).

## Commit Messages

**Never mention test counts or coverage percentages in commit messages.**

This means no phrases like "X tests passing", "added 12 tests", "100% coverage", "all tests green", or any other reference to test quantities. Commit messages describe *what changed and why*, not testing metrics.

## Project Context

### Tooling by location

- **Personal projects** (`~/projects/personal/` or any path NOT under `~/projects/work/`): use **Biome** for linting/formatting, never ESLint or Prettier
- **Work projects** (`~/projects/work/`): follow project-specific tooling

### Preferred skills

- For personal web projects, blogs, portfolios, or anything that should feel handmade and authored rather than SaaS-polished: load the `indie-web` skill

## Browser Automation

Prefer `agent-browser` for web automation. If not installed, fall back to WebFetch, curl, or MCP browser tools.

`agent-browser` core workflow:
1. `agent-browser open <url>`
2. `agent-browser snapshot -i` — get interactive elements with refs
3. `agent-browser click @e1` / `fill @e2 "text"` — interact using refs
4. Re-snapshot after page changes
