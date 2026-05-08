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

    distance = edit_distance(primary_tokens, secondary_tokens)
    longest = max(len(primary_tokens), len(secondary_tokens), 1)
    primary_reference_wer = distance / max(len(primary_tokens), 1)
    secondary_reference_wer = distance / max(len(secondary_tokens), 1)
    return {
        "primary_tokens": [asdict(token) for token in primary_view],
        "secondary_tokens": [asdict(token) for token in secondary_view],
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "edit_distance": distance,
        "primary_reference_wer": primary_reference_wer,
        "secondary_reference_wer": secondary_reference_wer,
        "relative_wer": distance / longest,
        "similarity": max(0.0, 1.0 - (distance / longest)),
    }


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    rows = len(reference) + 1
    cols = len(hypothesis) + 1
    matrix = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        matrix[i][0] = i
    for j in range(cols):
        matrix[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            substitution_cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + substitution_cost,
            )
    return matrix[-1][-1]
