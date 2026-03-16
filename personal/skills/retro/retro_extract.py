#!/usr/bin/env python3
"""Extract and summarise coding session data from OpenCode's SQLite database.

OpenCode (v1.2.25+) stores all session data in a single SQLite database rather
than per-session .jsonl files. This script replaces the upstream retro_extract.py
with one that reads from that database.

Database location: ~/.local/share/opencode/opencode.db
Override:          RETRO_OPENCODE_DB=/path/to/opencode.db

Schema (relevant tables):
  session  — id, slug, title, directory, time_created, time_updated, ...
  message  — id, session_id, time_created, data (JSON: role, model, tokens, ...)
  part     — id, message_id, session_id, time_created, data (JSON: type, text/tool, ...)

Part types:
  text        — prose (user prompts, assistant narrative)
  tool        — tool call + result (data.tool = tool name, data.state.input = args)
  step-start  — assistant turn boundary marker
  step-finish — assistant turn boundary marker
  reasoning   — extended thinking block

Usage:
    python retro_extract.py [project_path] --last N
    python retro_extract.py [project_path] --session-id <ID-or-prefix>
    python retro_extract.py [project_path] --list
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def get_db_path() -> Path:
    """Return the OpenCode SQLite database path.

    Respects the RETRO_OPENCODE_DB environment variable for non-standard
    install locations.
    """
    env = os.environ.get("RETRO_OPENCODE_DB", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    if not db_path.exists():
        print(f"OpenCode database not found at {db_path}", file=sys.stderr)
        print("Set RETRO_OPENCODE_DB to point at your opencode.db.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Session discovery
# ---------------------------------------------------------------------------


def list_sessions(project_path: str) -> list[dict]:
    """Return sessions for a project path, newest first.

    Matches on exact directory or any subdirectory. Falls back to all sessions
    when no project-specific sessions are found (e.g. when called from outside
    a project directory).
    """
    abs_path = os.path.abspath(project_path)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, slug, title, directory, time_created, time_updated
            FROM session
            WHERE directory = ? OR directory LIKE ?
            ORDER BY time_created DESC
            """,
            (abs_path, abs_path + "/%"),
        ).fetchall()

        if not rows:
            rows = conn.execute(
                """
                SELECT id, slug, title, directory, time_created, time_updated
                FROM session
                ORDER BY time_created DESC
                """
            ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_session_by_id_prefix(session_id: str) -> dict | None:
    """Find a session by its full ID or a unique prefix."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, slug, title, directory, time_created, time_updated
            FROM session
            WHERE id = ? OR id LIKE ?
            ORDER BY time_created DESC
            LIMIT 1
            """,
            (session_id, session_id + "%"),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Session parsing
# ---------------------------------------------------------------------------


def parse_session(session_id: str) -> dict:
    """Build a structured summary of a session from the SQLite database."""
    conn = get_connection()
    try:
        session_row = conn.execute(
            "SELECT * FROM session WHERE id = ?", (session_id,)
        ).fetchone()
        if not session_row:
            raise ValueError(f"Session {session_id!r} not found in database")
        session_meta = dict(session_row)

        messages = conn.execute(
            """
            SELECT id, time_created, data
            FROM message
            WHERE session_id = ?
            ORDER BY time_created ASC
            """,
            (session_id,),
        ).fetchall()

        parts = conn.execute(
            """
            SELECT message_id, time_created, data
            FROM part
            WHERE session_id = ?
            ORDER BY time_created ASC
            """,
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    # Index parts by message_id for O(1) lookup
    parts_by_msg: dict[str, list[dict]] = {}
    for part in parts:
        mid = part["message_id"]
        if mid not in parts_by_msg:
            parts_by_msg[mid] = []
        try:
            parts_by_msg[mid].append(json.loads(part["data"]))
        except (json.JSONDecodeError, TypeError):
            pass

    tool_counts: Counter = Counter()
    user_messages: list[dict] = []
    git_commits: list[str] = []
    skills_invoked: list[str] = []
    timestamps: list[int] = []
    turns = 0

    for msg_row in messages:
        try:
            msg_data = json.loads(msg_row["data"])
        except (json.JSONDecodeError, TypeError):
            continue

        role = msg_data.get("role", "unknown")
        ts: int | None = msg_row["time_created"]
        if ts:
            timestamps.append(ts)

        msg_parts = parts_by_msg.get(msg_row["id"], [])

        if role == "user":
            turns += 1
            text_parts = [
                p.get("text", "")
                for p in msg_parts
                if p.get("type") == "text" and p.get("text")
            ]
            text = " ".join(text_parts).strip()
            if text:
                ts_label = (
                    datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%H:%M")
                    if ts
                    else ""
                )
                user_messages.append({"text": text[:500], "timestamp": ts_label})

        elif role == "assistant":
            for part in msg_parts:
                if part.get("type") != "tool":
                    continue

                tool_name = part.get("tool", "unknown")
                tool_counts[tool_name] += 1

                state = part.get("state", {})
                inp = state.get("input", {}) if isinstance(state, dict) else {}

                # Detect git commits via bash tool
                if tool_name in ("bash", "mcp_bash"):
                    cmd = inp.get("command", "")
                    if "git commit" in cmd:
                        git_commits.append(cmd[:200])

                # Detect skill and task invocations
                if tool_name in ("mcp_skill", "mcp_task"):
                    label = inp.get("name") or inp.get("description", "")[:60]
                    skills_invoked.append(f"{tool_name}: {label}")

    duration = _format_duration(timestamps)

    return {
        "session_id": session_id,
        "metadata": {
            "slug": session_meta.get("slug", ""),
            "title": session_meta.get("title", ""),
            "directory": session_meta.get("directory", ""),
            "version": session_meta.get("version", ""),
        },
        "duration": duration,
        "turns": turns,
        "tool_counts": dict(sorted(tool_counts.items(), key=lambda x: -x[1])),
        "user_messages": user_messages,
        "git_commits": git_commits,
        "skills_invoked": list(set(skills_invoked)),
    }


def _format_duration(timestamps: list[int]) -> str:
    if len(timestamps) < 2:
        return ""
    delta_s = (max(timestamps) - min(timestamps)) / 1000
    minutes = int(delta_s / 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h {minutes % 60}m"


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_session_summary(session: dict) -> str:
    meta = session["metadata"]
    lines: list[str] = []

    lines.append(f"# Session: {session['session_id']}")
    if meta.get("title"):
        lines.append(f"**Title**: {meta['title']}")
    if meta.get("slug"):
        lines.append(f"**Slug**: {meta['slug']}")
    lines.append("")

    lines.append("## Metadata")
    lines.append("")
    if meta.get("directory"):
        lines.append(f"- **Working Dir**: `{meta['directory']}`")
    if meta.get("version"):
        lines.append(f"- **Version**: {meta['version']}")
    if session.get("duration"):
        lines.append(f"- **Duration**: {session['duration']}")
    lines.append(f"- **Turns**: {session['turns']}")
    lines.append("")

    if session["tool_counts"]:
        lines.append("## Tool Usage")
        lines.append("")
        for tool, count in session["tool_counts"].items():
            lines.append(f"- **{tool}**: {count}")
        lines.append("")

    if session["skills_invoked"]:
        lines.append("## Skills / Tasks Invoked")
        lines.append("")
        for skill in session["skills_invoked"]:
            lines.append(f"- {skill}")
        lines.append("")

    if session["git_commits"]:
        lines.append("## Git Commits")
        lines.append("")
        for commit in session["git_commits"]:
            lines.append(f"- `{commit}`")
        lines.append("")

    if session["user_messages"]:
        lines.append("## Conversation Flow (User Messages)")
        lines.append("")
        for i, msg in enumerate(session["user_messages"], 1):
            text = msg["text"].replace("\n", " ")[:200]
            ts = msg.get("timestamp", "")
            prefix = f"[{ts}] " if ts else ""
            lines.append(f"{i}. {prefix}{text}")
        lines.append("")

    return "\n".join(lines)


def format_session_list(sessions: list[dict]) -> str:
    if not sessions:
        return "No sessions found."

    lines: list[str] = ["# Available Sessions", ""]
    lines.append("| # | Date (UTC) | Slug | Title | Session ID |")
    lines.append("|---|------------|------|-------|------------|")

    for i, s in enumerate(sessions, 1):
        dt = datetime.fromtimestamp(
            s["time_created"] / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M")
        slug = (s.get("slug") or "")[:20]
        title = (s.get("title") or "")[:30]
        sid = s["id"][:12] + "…"
        lines.append(f"| {i} | {dt} | {slug} | {title} | `{sid}` |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract and summarise OpenCode session data from the local SQLite database"
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Project path — filters sessions by working directory (default: .)",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Analyse the N most recent sessions (default: 1, max: 5)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Analyse a specific session by full ID or unique prefix",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available sessions without parsing them",
    )

    args = parser.parse_args()

    if args.list:
        sessions = list_sessions(args.project_path)
        print(format_session_list(sessions))
        return

    if args.session_id:
        session_meta = find_session_by_id_prefix(args.session_id)
        if not session_meta:
            print(f"Session {args.session_id!r} not found.", file=sys.stderr)
            sys.exit(1)
        session = parse_session(session_meta["id"])
        print(format_session_summary(session))
        return

    n = min(args.last or 1, 5)
    sessions = list_sessions(args.project_path)

    if not sessions:
        print("No sessions found.", file=sys.stderr)
        sys.exit(1)

    for s in sessions[:n]:
        session = parse_session(s["id"])
        print(format_session_summary(session))
        if n > 1:
            print("---")
            print("")


if __name__ == "__main__":
    main()
