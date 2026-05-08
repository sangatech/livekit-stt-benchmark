from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher


@dataclass(slots=True)
class DiffToken:
    token: str
    kind: str
    provider: str


def tokenize(text: str) -> list[str]:
    return [part for part in text.strip().split() if part]


def compare_transcripts(primary: str, secondary: str) -> dict[str, object]:
    primary_tokens = tokenize(primary.lower())
    secondary_tokens = tokenize(secondary.lower())
    matcher = SequenceMatcher(a=primary_tokens, b=secondary_tokens, autojunk=False)
    primary_view: list[DiffToken] = []
    secondary_view: list[DiffToken] = []
    substitutions = insertions = deletions = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            primary_view.extend(DiffToken(token=t, kind="equal", provider="primary") for t in primary_tokens[i1:i2])
            secondary_view.extend(DiffToken(token=t, kind="equal", provider="secondary") for t in secondary_tokens[j1:j2])
        elif tag == "replace":
            substitutions += max(i2 - i1, j2 - j1)
            primary_view.extend(DiffToken(token=t, kind="substitution", provider="primary") for t in primary_tokens[i1:i2])
            secondary_view.extend(DiffToken(token=t, kind="substitution", provider="secondary") for t in secondary_tokens[j1:j2])
        elif tag == "delete":
            deletions += i2 - i1
            primary_view.extend(DiffToken(token=t, kind="missing", provider="primary") for t in primary_tokens[i1:i2])
        elif tag == "insert":
            insertions += j2 - j1
            secondary_view.extend(DiffToken(token=t, kind="hallucination", provider="secondary") for t in secondary_tokens[j1:j2])

    distance = substitutions + insertions + deletions
    longest = max(len(primary_tokens), len(secondary_tokens), 1)
    return {
        "primary_tokens": [asdict(token) for token in primary_view],
        "secondary_tokens": [asdict(token) for token in secondary_view],
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "similarity": max(0.0, 1.0 - (distance / longest)),
    }
