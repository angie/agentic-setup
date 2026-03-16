#!/usr/bin/env python3
"""Extract and summarise coding session data from local coding assistants.

Supports two backends, auto-detected by what's available on disk:

  opencode  — OpenCode v1.2.25+: SQLite at ~/.local/share/opencode/opencode.db
  jsonl     — Claude Code / Windsurf / Codex: per-session .jsonl files

Both backends are queried when listing or analysing sessions. parse_session()
dispatches to the correct backend based on the session ID format:
  OpenCode IDs start with "ses_"   (e.g. ses_30a0615a2ffe...)
  .jsonl IDs are UUIDs             (e.g. a1b2c3d4-e5f6-7890...)

Environment variables:
  RETRO_OPENCODE_DB     Override the default OpenCode database path.
  RETRO_SESSION_ROOTS   Colon-separated list of .jsonl project root dirs
                        (default: ~/.claude/projects, ~/.codeium/windsurf/projects,
                        ~/.codex/projects).

Usage:
    python retro_extract.py [project_path] --last N
    python retro_extract.py [project_path] --session-id <ID-or-prefix>
    python retro_extract.py [project_path] --list
    python retro_extract.py [project_path] --list --all-projects
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
# OpenCode backend  (SQLite)
# ---------------------------------------------------------------------------

_OPENCODE_DB_DEFAULT = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _opencode_db_path() -> Path:
    env = os.environ.get("RETRO_OPENCODE_DB", "").strip()
    return Path(env).expanduser() if env else _OPENCODE_DB_DEFAULT


def _opencode_available() -> bool:
    return _opencode_db_path().exists()


def _opencode_connect() -> sqlite3.Connection:
    db = _opencode_db_path()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _opencode_list_sessions(project_path: str) -> list[dict]:
    abs_path = os.path.abspath(project_path)
    conn = _opencode_connect()
    try:
        rows = conn.execute(
            """
            SELECT id, slug, title, directory, time_created
            FROM session
            WHERE directory = ? OR directory LIKE ?
            ORDER BY time_created DESC
            """,
            (abs_path, abs_path + "/%"),
        ).fetchall()

        if not rows:
            rows = conn.execute(
                """
                SELECT id, slug, title, directory, time_created
                FROM session
                ORDER BY time_created DESC
                """
            ).fetchall()

        return [
            {
                "id": r["id"],
                "slug": r["slug"] or "",
                "title": r["title"] or "",
                "directory": r["directory"] or "",
                "time_created": r["time_created"],  # epoch ms
                "_backend": "opencode",
            }
            for r in rows
        ]
    finally:
        conn.close()


def _opencode_find_by_prefix(session_id: str) -> dict | None:
    conn = _opencode_connect()
    try:
        row = conn.execute(
            """
            SELECT id, slug, title, directory, time_created
            FROM session
            WHERE id = ? OR id LIKE ?
            ORDER BY time_created DESC
            LIMIT 1
            """,
            (session_id, session_id + "%"),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "slug": row["slug"] or "",
            "title": row["title"] or "",
            "directory": row["directory"] or "",
            "time_created": row["time_created"],
            "_backend": "opencode",
        }
    finally:
        conn.close()


def _opencode_parse(session_id: str) -> dict:
    conn = _opencode_connect()
    try:
        session_row = conn.execute(
            "SELECT * FROM session WHERE id = ?", (session_id,)
        ).fetchone()
        if not session_row:
            raise ValueError(f"OpenCode session {session_id!r} not found")
        meta = dict(session_row)

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
            text = " ".join(
                p.get("text", "")
                for p in msg_parts
                if p.get("type") == "text" and p.get("text")
            ).strip()
            if text:
                ts_label = (
                    datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%H:%M")
                    if ts else ""
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
                if tool_name in ("bash", "mcp_bash"):
                    cmd = inp.get("command", "")
                    if "git commit" in cmd:
                        git_commits.append(cmd[:200])
                if tool_name in ("mcp_skill", "mcp_task"):
                    label = inp.get("name") or inp.get("description", "")[:60]
                    skills_invoked.append(f"{tool_name}: {label}")

    return {
        "session_id": session_id,
        "metadata": {
            "slug": meta.get("slug", ""),
            "title": meta.get("title", ""),
            "branch": "",
            "cwd": meta.get("directory", ""),
            "version": meta.get("version", ""),
        },
        "duration": _format_duration_ms(timestamps),
        "turns": turns,
        "tool_counts": dict(sorted(tool_counts.items(), key=lambda x: -x[1])),
        "user_messages": user_messages,
        "git_commits": git_commits,
        "skills_invoked": list(set(skills_invoked)),
        "_backend": "opencode",
    }


# ---------------------------------------------------------------------------
# .jsonl backend  (Claude Code / Windsurf / Codex)
# ---------------------------------------------------------------------------

_JSONL_DEFAULT_ROOTS = [
    Path.home() / ".claude" / "projects",
    Path.home() / ".codeium" / "windsurf" / "projects",
    Path.home() / ".codex" / "projects",
]


def _jsonl_roots() -> list[Path]:
    env = os.environ.get("RETRO_SESSION_ROOTS", "").strip()
    if env:
        roots = [Path(e).expanduser() for e in env.split(os.pathsep) if e.strip()]
    else:
        roots = _JSONL_DEFAULT_ROOTS
    return [r for r in roots if r.is_dir()]


def _jsonl_available() -> bool:
    return bool(_jsonl_roots())


def _encode_project_path(project_path: str) -> str:
    return os.path.abspath(project_path).replace("/", "-")


def _jsonl_project_dirs(project_path: str) -> list[Path]:
    encoded = _encode_project_path(project_path)
    dirs: list[Path] = []
    for root in _jsonl_roots():
        for d in root.iterdir():
            if d.is_dir() and encoded in d.name:
                dirs.append(d)
    return dirs


def _jsonl_peek_metadata(jsonl_file: Path) -> dict:
    meta = {"branch": "", "version": "", "cwd": "", "slug": ""}
    try:
        with open(jsonl_file) as f:
            for i, line in enumerate(f):
                if i > 20:
                    break
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("gitBranch") and not meta["branch"]:
                    meta["branch"] = r["gitBranch"]
                if r.get("version") and not meta["version"]:
                    meta["version"] = r["version"]
                if r.get("cwd") and not meta["cwd"]:
                    meta["cwd"] = r["cwd"]
                if r.get("slug") and not meta["slug"]:
                    meta["slug"] = r["slug"]
    except (OSError, UnicodeDecodeError):
        pass
    return meta


def _jsonl_list_sessions(project_path: str) -> list[dict]:
    project_dirs = _jsonl_project_dirs(project_path)

    if not project_dirs:
        # Fall back to all projects across all roots
        for root in _jsonl_roots():
            project_dirs.extend(d for d in root.iterdir() if d.is_dir())

    sessions: list[dict] = []
    for project_dir in project_dirs:
        for jsonl_file in project_dir.glob("*.jsonl"):
            if "subagents" in str(jsonl_file):
                continue
            mtime_ms = int(jsonl_file.stat().st_mtime * 1000)
            peek = _jsonl_peek_metadata(jsonl_file)
            sessions.append(
                {
                    "id": jsonl_file.stem,
                    "slug": peek.get("slug", ""),
                    "title": peek.get("slug", ""),  # .jsonl has no separate title
                    "directory": peek.get("cwd", ""),
                    "time_created": mtime_ms,
                    "_backend": "jsonl",
                    "_path": str(jsonl_file),
                    "_branch": peek.get("branch", ""),
                    "_version": peek.get("version", ""),
                }
            )

    sessions.sort(key=lambda s: s["time_created"], reverse=True)
    return sessions


def _jsonl_find_by_prefix(session_id: str) -> dict | None:
    for root in _jsonl_roots():
        for project_dir in root.iterdir():
            if not project_dir.is_dir():
                continue
            for candidate in project_dir.glob(f"{session_id}*.jsonl"):
                if candidate.exists():
                    mtime_ms = int(candidate.stat().st_mtime * 1000)
                    peek = _jsonl_peek_metadata(candidate)
                    return {
                        "id": candidate.stem,
                        "slug": peek.get("slug", ""),
                        "title": peek.get("slug", ""),
                        "directory": peek.get("cwd", ""),
                        "time_created": mtime_ms,
                        "_backend": "jsonl",
                        "_path": str(candidate),
                        "_branch": peek.get("branch", ""),
                        "_version": peek.get("version", ""),
                    }
    return None


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts).strip()
    return ""


def _jsonl_parse(jsonl_path: str) -> dict:
    records: list[dict] = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        raise ValueError(f"Cannot read {jsonl_path}: {e}") from e

    tool_counts: Counter = Counter()
    user_messages: list[dict] = []
    git_commits: list[str] = []
    skills_invoked: list[str] = []
    timestamps: list[str] = []
    meta = {"branch": "", "version": "", "cwd": "", "slug": ""}

    for record in records:
        rtype = record.get("type", "unknown")

        if record.get("gitBranch") and not meta["branch"]:
            meta["branch"] = record["gitBranch"]
        if record.get("version") and not meta["version"]:
            meta["version"] = record["version"]
        if record.get("cwd") and not meta["cwd"]:
            meta["cwd"] = record["cwd"]
        if record.get("slug") and not meta["slug"]:
            meta["slug"] = record["slug"]

        ts = record.get("timestamp")
        if ts:
            timestamps.append(ts)

        msg = record.get("message", {})
        if not isinstance(msg, dict):
            msg = {}
        content = msg.get("content", [])

        if rtype == "user" and not record.get("isMeta"):
            text = _extract_text(content)
            if text and not text.startswith("<local-command"):
                ts_label = ""
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        ts_label = dt.strftime("%H:%M")
                    except ValueError:
                        pass
                user_messages.append({"text": text[:500], "timestamp": ts_label})

        elif rtype == "assistant":
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_counts[tool_name] += 1
                        if tool_name == "Bash":
                            cmd = block.get("input", {}).get("command", "")
                            if "git commit" in cmd:
                                git_commits.append(cmd[:200])
                        if tool_name == "Agent":
                            task = block.get("input", {}).get("task", "")[:100]
                            skills_invoked.append(f"Agent: {task}")

        elif rtype == "progress":
            data = record.get("data", {})
            if isinstance(data, dict) and data.get("type") == "hook_progress":
                hook = data.get("hookName", "")
                if hook:
                    skills_invoked.append(f"Hook: {hook}")

    duration = _format_duration_iso(timestamps)
    turns = sum(1 for r in records if r.get("type") == "user" and not r.get("isMeta"))

    return {
        "session_id": Path(jsonl_path).stem,
        "metadata": {
            "slug": meta["slug"],
            "title": meta["slug"],
            "branch": meta["branch"],
            "cwd": meta["cwd"],
            "version": meta["version"],
        },
        "duration": duration,
        "turns": turns,
        "tool_counts": dict(sorted(tool_counts.items(), key=lambda x: -x[1])),
        "user_messages": user_messages,
        "git_commits": git_commits,
        "skills_invoked": list(set(skills_invoked)),
        "_backend": "jsonl",
    }


# ---------------------------------------------------------------------------
# Unified session listing + parsing
# ---------------------------------------------------------------------------


def list_sessions(project_path: str, all_projects: bool = False) -> list[dict]:
    """Return sessions from all available backends, newest first."""
    sessions: list[dict] = []

    if _opencode_available():
        sessions.extend(_opencode_list_sessions(project_path))

    if _jsonl_available():
        jsonl = _jsonl_list_sessions(project_path)
        if all_projects and not jsonl:
            # Replicate upstream --all-projects fallback
            for root in _jsonl_roots():
                for d in root.iterdir():
                    if d.is_dir():
                        for f in d.glob("*.jsonl"):
                            if "subagents" not in str(f):
                                mtime_ms = int(f.stat().st_mtime * 1000)
                                peek = _jsonl_peek_metadata(f)
                                jsonl.append({
                                    "id": f.stem,
                                    "slug": peek.get("slug", ""),
                                    "title": peek.get("slug", ""),
                                    "directory": peek.get("cwd", ""),
                                    "time_created": mtime_ms,
                                    "_backend": "jsonl",
                                    "_path": str(f),
                                    "_branch": peek.get("branch", ""),
                                    "_version": peek.get("version", ""),
                                })
        sessions.extend(jsonl)

    sessions.sort(key=lambda s: s["time_created"], reverse=True)
    return sessions


def find_session(session_id: str) -> dict | None:
    """Find a session by ID or prefix across all available backends."""
    # OpenCode IDs always start with "ses_"
    if session_id.startswith("ses_"):
        if _opencode_available():
            return _opencode_find_by_prefix(session_id)
        return None

    # Otherwise assume .jsonl UUID
    if _jsonl_available():
        return _jsonl_find_by_prefix(session_id)
    return None


def parse_session(session: dict) -> dict:
    """Parse a session into a unified summary dict, dispatching by backend."""
    backend = session.get("_backend", "")
    if backend == "opencode":
        return _opencode_parse(session["id"])
    if backend == "jsonl":
        return _jsonl_parse(session["_path"])
    raise ValueError(f"Unknown backend {backend!r} for session {session['id']}")


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def _format_duration_ms(timestamps: list[int]) -> str:
    if len(timestamps) < 2:
        return ""
    minutes = int((max(timestamps) - min(timestamps)) / 1000 / 60)
    return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"


def _format_duration_iso(timestamps: list[str]) -> str:
    if len(timestamps) < 2:
        return ""
    try:
        parsed = sorted(
            datetime.fromisoformat(t.replace("Z", "+00:00")) for t in timestamps
        )
        minutes = int((parsed[-1] - parsed[0]).total_seconds() / 60)
        return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"
    except (ValueError, IndexError):
        return ""


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_session_summary(session: dict) -> str:
    meta = session["metadata"]
    lines: list[str] = []

    lines.append(f"# Session: {session['session_id']}")
    title = meta.get("title") or meta.get("slug", "")
    if title:
        lines.append(f"**Title**: {title}")
    if meta.get("slug") and meta.get("slug") != title:
        lines.append(f"**Slug**: {meta['slug']}")
    lines.append("")

    lines.append("## Metadata")
    lines.append("")
    cwd = meta.get("cwd") or meta.get("directory", "")
    if cwd:
        lines.append(f"- **Working Dir**: `{cwd}`")
    if meta.get("branch"):
        lines.append(f"- **Branch**: `{meta['branch']}`")
    if meta.get("version"):
        lines.append(f"- **Version**: {meta['version']}")
    if session.get("duration"):
        lines.append(f"- **Duration**: {session['duration']}")
    lines.append(f"- **Turns**: {session['turns']}")
    lines.append(f"- **Source**: {session.get('_backend', 'unknown')}")
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
    lines.append("| # | Date (UTC) | Source | Slug / Title | Session ID |")
    lines.append("|---|------------|--------|--------------|------------|")

    for i, s in enumerate(sessions, 1):
        dt = datetime.fromtimestamp(
            s["time_created"] / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M")
        source = s.get("_backend", "?")
        label = (s.get("title") or s.get("slug", ""))[:30]
        sid = s["id"][:12] + "…"
        lines.append(f"| {i} | {dt} | {source} | {label} | `{sid}` |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if not _opencode_available() and not _jsonl_available():
        print(
            "No session data found. Expected one of:\n"
            f"  OpenCode DB:  {_opencode_db_path()}\n"
            f"  .jsonl roots: {[str(r) for r in _JSONL_DEFAULT_ROOTS]}\n"
            "Set RETRO_OPENCODE_DB or RETRO_SESSION_ROOTS to override.",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Extract and summarise coding session data (OpenCode + Claude Code / Windsurf / Codex)"
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
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Search across all projects, not just the specified path",
    )

    args = parser.parse_args()

    if args.list:
        sessions = list_sessions(args.project_path, all_projects=args.all_projects)
        print(format_session_list(sessions))
        return

    if args.session_id:
        session_meta = find_session(args.session_id)
        if not session_meta:
            print(f"Session {args.session_id!r} not found.", file=sys.stderr)
            sys.exit(1)
        result = parse_session(session_meta)
        print(format_session_summary(result))
        return

    n = min(args.last or 1, 5)
    sessions = list_sessions(args.project_path, all_projects=args.all_projects)

    if not sessions:
        print("No sessions found.", file=sys.stderr)
        sys.exit(1)

    for s in sessions[:n]:
        result = parse_session(s)
        print(format_session_summary(result))
        if n > 1:
            print("---")
            print("")


if __name__ == "__main__":
    main()
