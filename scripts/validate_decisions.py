#!/usr/bin/env python3
"""Validate docs/decisions.md schema, tag vocabulary, and reference integrity.

Exit code 0 = clean. Non-zero = errors printed to stderr.

Designed for use in three layers:
  - Layer 1 (in-skill): invoked at the end of decision-capture as a self-audit.
  - Layer 2 (pre-commit): runs when docs/decisions.md changes.
  - Layer 3 (periodic review): part of a manual or scheduled review pass.

Checks performed:
  - Required fields present on every entry (Type, Door Type, Decision,
    Rationale, Source, Status).
  - Type is a single primary value (not a slash-pair like "scope / process").
  - Tags only contain values from the canonical vocabulary (if a
    `## Tag vocabulary` section exists in the file).
  - Status values match a recognized pattern (active / open / deprecated /
    superseded by D-NN, optionally with a trailing clause).
  - Supersession integrity: every `superseded by D-NN` reference targets
    a real entry.
  - Reference integrity: every D-NN mention in entry bodies resolves to
    a real entry.
  - No duplicate IDs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Repo root: this script lives in scripts/, decisions.md lives in docs/.
DECISIONS_FILE = Path(__file__).resolve().parent.parent / "docs" / "decisions.md"

# Fields required on every entry regardless of status.
REQUIRED_FIELDS_ALWAYS = ["Type", "Door Type", "Decision", "Source", "Status"]
# Rationale is required only for active entries — open placeholders haven't
# been resolved yet; superseded/deprecated entries may predate the requirement
# or have been retired without individual resolution.
REQUIRED_FIELDS_ACTIVE_ONLY = ["Rationale"]

# Valid Status forms. Order doesn't matter; any match wins.
STATUS_PATTERNS = [
    re.compile(r"^active$"),
    re.compile(r"^active\b.*"),                     # active; supersedes D-N on ...
    re.compile(r"^open$"),
    re.compile(r"^open\b.*"),                       # open; awaiting decision on ...
    re.compile(r"^deprecated$"),
    re.compile(r"^superseded by D-\d+$"),
    re.compile(r"^superseded by D-\d+\b.*"),
    re.compile(r"^partially superseded by D-\d+$"),
    re.compile(r"^partially superseded by D-\d+\b.*"),
]


class DecisionEntry:
    __slots__ = ("id", "title", "fields", "body")

    def __init__(self, id_: int, title: str, fields: dict, body: str):
        self.id = id_
        self.title = title
        self.fields = fields
        self.body = body

    def __repr__(self) -> str:
        return f"D-{self.id:02d}"


def parse_decisions(text: str) -> list[DecisionEntry]:
    """Split decisions.md by '### D-NN:' headers and parse each entry."""
    entries: list[DecisionEntry] = []
    chunks = re.split(r"^### D-(\d+):\s*(.+)$", text, flags=re.MULTILINE)
    # chunks[0] is preamble; thereafter triples of (id, title, body).
    for i in range(1, len(chunks), 3):
        id_ = int(chunks[i])
        title = chunks[i + 1].strip()
        body = chunks[i + 2]
        # Trim body at the next '## ' section header (so trailing
        # Cross-references / Tag vocabulary doesn't leak into the last entry).
        next_section = re.search(r"^## ", body, flags=re.MULTILINE)
        if next_section:
            body = body[: next_section.start()]
        fields = _parse_fields(body)
        entries.append(DecisionEntry(id_, title, fields, body))
    return entries


def _parse_fields(body: str) -> dict:
    """Extract **Field:** value pairs from an entry body."""
    fields: dict[str, str] = {}
    # Match **Field:** followed by value text up to the next blank line OR
    # the next **Field:** line. Inline-only values for the validator's needs.
    for match in re.finditer(
        r"^\*\*([^*]+?):\*\*\s*(.+?)(?=\n\n|\n\*\*|\Z)",
        body,
        flags=re.MULTILINE | re.DOTALL,
    ):
        key = match.group(1).strip()
        value = match.group(2).strip()
        fields[key] = value
    return fields


def parse_tag_vocabulary(text: str) -> set[str] | None:
    """Extract canonical tags from the `## Tag vocabulary` section.

    Returns None if the section doesn't exist (skip tag validation in that case).
    """
    section_match = re.search(
        r"^## Tag vocabulary\b(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not section_match:
        return None
    section = section_match.group(1)
    tags: set[str] = set()
    for m in re.finditer(r"^\s*[-*]\s*`([a-z0-9_-]+)`", section, flags=re.MULTILINE):
        tags.add(m.group(1))
    return tags


def validate(entries: list[DecisionEntry], vocab: set[str] | None) -> list[str]:
    """Run all checks; return a list of error strings (empty = clean)."""
    errors: list[str] = []
    seen_ids: set[int] = set()
    all_ids: set[int] = {e.id for e in entries}

    for e in entries:
        prefix = f"D-{e.id:02d}"

        if e.id in seen_ids:
            errors.append(f"{prefix}: duplicate ID")
        seen_ids.add(e.id)

        for field in REQUIRED_FIELDS_ALWAYS:
            if field not in e.fields or not e.fields[field].strip():
                errors.append(f"{prefix}: missing required field '{field}'")

        status = e.fields.get("Status", "")
        if status.startswith("active"):
            for field in REQUIRED_FIELDS_ACTIVE_ONLY:
                if field not in e.fields or not e.fields[field].strip():
                    errors.append(
                        f"{prefix}: missing required field '{field}' "
                        "(required for active entries)"
                    )

        type_val = e.fields.get("Type", "")
        if "/" in type_val:
            errors.append(
                f"{prefix}: Type contains slash-pair '{type_val}' — "
                "pick a single primary value (secondary categories go in Tags)"
            )

        if status and not any(p.match(status) for p in STATUS_PATTERNS):
            errors.append(f"{prefix}: invalid Status value '{status}'")

        for ref_id in _extract_superseded_by_targets(status):
            if ref_id not in all_ids:
                errors.append(
                    f"{prefix}: status references D-{ref_id:02d} as supersession "
                    "target but no such entry exists"
                )

        if vocab is not None and "Tags" in e.fields:
            for tag in (t.strip() for t in e.fields["Tags"].split(",")):
                if tag and tag not in vocab:
                    errors.append(
                        f"{prefix}: tag '{tag}' not in canonical vocabulary "
                        "(see ## Tag vocabulary section)"
                    )

    # Reference integrity across all entry bodies.
    for e in entries:
        for ref_id in _extract_dn_references(e.body):
            if ref_id not in all_ids:
                errors.append(
                    f"D-{e.id:02d}: body references D-{ref_id:02d} which doesn't exist"
                )

    return errors


def _extract_superseded_by_targets(status: str) -> list[int]:
    """Find D-NN ids in 'superseded by D-NN' phrases inside a Status value."""
    return [int(m.group(1)) for m in re.finditer(r"superseded by D-(\d+)", status)]


def _extract_dn_references(body: str) -> list[int]:
    """Find every D-NN reference in a body chunk."""
    return [int(m.group(1)) for m in re.finditer(r"\bD-(\d+)\b", body)]


def main() -> int:
    if not DECISIONS_FILE.exists():
        print(f"error: {DECISIONS_FILE} not found", file=sys.stderr)
        return 2

    text = DECISIONS_FILE.read_text()
    entries = parse_decisions(text)
    vocab = parse_tag_vocabulary(text)

    print(f"validating {len(entries)} decisions in {DECISIONS_FILE.relative_to(DECISIONS_FILE.parents[1])}")
    if vocab is not None:
        print(f"tag vocabulary: {len(vocab)} canonical tags")
    else:
        print("no '## Tag vocabulary' section found — tag checks skipped")

    errors = validate(entries, vocab)

    if errors:
        print(f"\n{len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("OK — no errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
