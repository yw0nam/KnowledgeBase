"""Append User Feedback lines to wiki page bodies.

Body convention (see spec §6.3):

    ## User Feedback

    2026-05-19-Rejected: <text>
    2026-05-20-Approved: <text>
    2026-05-21-Auto-rejected: <system reason>

A single section accumulates lines from multiple review actions.
Empty input means "skip" — no line is appended (avoids noise).
"""

from __future__ import annotations

from pathlib import Path

HEADER = "## User Feedback"


def append_feedback_line(path: Path, date_str: str, label: str, raw_input: str) -> None:
    """Append a feedback line of the form ``YYYY-MM-DD-Label: <text>``.

    If raw_input is empty/whitespace, the file is not modified.
    If the ## User Feedback section already exists, the line is appended
    inside it. Otherwise the section is created at end of body.
    """
    feedback = raw_input.strip()
    if not feedback:
        return

    line = f"{date_str}-{label}: {feedback}"
    text = path.read_text()

    if HEADER in text:
        # Append within the existing section, before any trailing blank lines.
        # Locate the User Feedback heading and the next ## heading (or EOF).
        header_idx = text.index(HEADER)
        # End-of-section: next top-level `## ` after the header, or EOF.
        rest_start = header_idx + len(HEADER)
        next_h = _find_next_h2(text, rest_start)
        section_end = next_h if next_h is not None else len(text)

        existing = text[header_idx:section_end].rstrip()
        new_section = existing + f"\n{line}\n"
        path.write_text(text[:header_idx] + new_section + text[section_end:])
        return

    # No existing section — append at end of body.
    body_trimmed = text.rstrip()
    new_text = body_trimmed + f"\n\n{HEADER}\n\n{line}\n"
    path.write_text(new_text)


def _find_next_h2(text: str, start: int) -> int | None:
    """Return the index of the next ``\\n## `` (level-2 heading) after start, or None."""
    needle = "\n## "
    idx = text.find(needle, start)
    return idx if idx >= 0 else None
