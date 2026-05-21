#!/usr/bin/env python3
"""Quick lookup tool for docs/decisions.md entries.

Usage:
  dx.py D-158                 # print entry D-158
  dx.py find <text>           # full-text search (case-insensitive)
  dx.py tag <tag>             # list entries with the given tag
  dx.py type <type>           # list entries with the given Type
  dx.py status <pattern>      # list entries where Status contains the pattern
  dx.py open                  # shortcut for status 'open'
  dx.py list                  # list every entry (id + title)

Drop a decision reference into chat / PR by piping:
  dx.py D-158 | pbcopy        # macOS
  dx.py D-158 | xclip -sel c  # linux
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DECISIONS_FILE = Path(__file__).resolve().parent.parent / "docs" / "decisions.md"


def parse_entries(text: str) -> list[dict]:
    entries: list[dict] = []
    chunks = re.split(r"^### D-(\d+):\s*(.+)$", text, flags=re.MULTILINE)
    for i in range(1, len(chunks), 3):
        id_ = int(chunks[i])
        title = chunks[i + 1].strip()
        body = chunks[i + 2]
        next_section = re.search(r"^## ", body, flags=re.MULTILINE)
        if next_section:
            body = body[: next_section.start()]
        entries.append({"id": id_, "title": title, "body": body.rstrip()})
    return entries


def get_field(body: str, field_name: str) -> str:
    match = re.search(
        rf"^\*\*{re.escape(field_name)}:\*\*\s*(.+?)(?=\n\n|\n\*\*|\Z)",
        body,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def cmd_show(entries: list[dict], target: str) -> int:
    target_id = int(re.sub(r"^[dD]-?", "", target))
    matches = [e for e in entries if e["id"] == target_id]
    if not matches:
        print(f"D-{target_id} not found", file=sys.stderr)
        return 1
    e = matches[0]
    print(f"### D-{e['id']}: {e['title']}\n")
    print(e["body"])
    return 0


def cmd_find(entries: list[dict], query: str) -> int:
    q = query.lower()
    matches = [
        e for e in entries
        if q in e["title"].lower() or q in e["body"].lower()
    ]
    if not matches:
        print(f"no matches for '{query}'", file=sys.stderr)
        return 1
    for e in matches:
        print(f"D-{e['id']:03d}: {e['title']}")
    return 0


def cmd_filter_field(entries: list[dict], field: str, value: str) -> int:
    v = value.lower()
    matches = []
    for e in entries:
        field_val = get_field(e["body"], field).lower()
        if field == "Tags":
            tags = [t.strip() for t in field_val.split(",")]
            if v in tags:
                matches.append(e)
        elif v in field_val:
            matches.append(e)
    if not matches:
        print(f"no entries with {field}: {value}", file=sys.stderr)
        return 1
    for e in matches:
        print(f"D-{e['id']:03d}: {e['title']}")
    return 0


def cmd_list(entries: list[dict]) -> int:
    for e in entries:
        print(f"D-{e['id']:03d}: {e['title']}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2

    text = DECISIONS_FILE.read_text()
    entries = parse_entries(text)

    arg = argv[0]
    if re.match(r"^[dD]-?\d+$", arg):
        return cmd_show(entries, arg)
    if arg == "list":
        return cmd_list(entries)
    if arg == "open":
        return cmd_filter_field(entries, "Status", "open")
    if len(argv) >= 2:
        if arg == "find":
            return cmd_find(entries, " ".join(argv[1:]))
        if arg == "tag":
            return cmd_filter_field(entries, "Tags", argv[1])
        if arg == "type":
            return cmd_filter_field(entries, "Type", argv[1])
        if arg == "status":
            return cmd_filter_field(entries, "Status", argv[1])

    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
