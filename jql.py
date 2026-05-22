from __future__ import annotations

import re

# membersOf( <arg> )  — arg may be quoted or bare
_MEMBERS_OF = re.compile(r'membersOf\(\s*("[^"]*"|\'[^\']*\'|[^)]*?)\s*\)', re.IGNORECASE)
# group <op> <value>   — value is a quoted string, a (...) list, or a bare token
_GROUP_OP = re.compile(
    r'\bgroup\b\s*(?:=|!=|\bnot\s+in\b|\bin\b)\s*'
    r'(\([^)]*\)|"[^"]*"|\'[^\']*\'|[^\s()]+)',
    re.IGNORECASE,
)


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] in "\"'" and token[-1] == token[0]:
        return token[1:-1]
    return token


def _candidates_in(value: str) -> list[str]:
    """Pull individual group tokens out of a matched value (handles (...) lists)."""
    value = value.strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    return [_unquote(part) for part in value.split(",") if part.strip()]


def find_group_references(jql: str, group_name: str, group_id: str) -> list[str]:
    """Return the matched clause substrings in `jql` that reference the group.

    Only structured references are considered:
      - membersOf("group" | groupId | group)
      - group = / != / in / not in  <value(s)>
    Bare substring occurrences (e.g. a project key) never match.
    """
    if not jql:
        return []
    name_cf = group_name.casefold()
    hits: list[str] = []

    def _maybe_add(clause: str, tokens: list[str]) -> None:
        for tok in tokens:
            if tok == group_id or tok.casefold() == name_cf:
                if clause not in hits:
                    hits.append(clause)
                return

    # collect matches with their start positions so output is in source order
    spans: list[tuple[int, str, list[str]]] = []
    for m in _MEMBERS_OF.finditer(jql):
        spans.append((m.start(), m.group(0), [_unquote(m.group(1))]))
    for m in _GROUP_OP.finditer(jql):
        spans.append((m.start(), m.group(0), _candidates_in(m.group(1))))

    for _start, clause, tokens in sorted(spans, key=lambda s: s[0]):
        _maybe_add(clause, tokens)
    return hits
