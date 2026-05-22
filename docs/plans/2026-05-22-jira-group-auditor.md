# Jira Group Auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a configurable, read-only Python tool that sweeps a Jira Cloud site for every place a given group is referenced (permissions, license roles, filters incl. JQL, dashboards, boards, notification/security schemes, project roles, group-picker custom fields) and emits, per group, a high-quality PDF report plus a JSON sidecar.

**Architecture:** Small focused modules in `jira-group-auditor/`. `jira_client.py` does authenticated paginated REST; `models.py` holds the typed `GroupAudit`; `jql.py`/`matchers.py`/`classify.py` are pure, unit-tested helpers (the risk areas); `sweep.py` runs the collectors and assembles a `GroupAudit` with per-dimension error isolation; `report.py`+`report_assets.py` render HTML→PDF (WeasyPrint) + JSON; `auditor.py` is the CLI. Dimensions with no public Cloud REST read endpoint become a "manual check" section.

**Tech Stack:** Python 3.12, `requests` 2.31, `weasyprint` 68.1, `pytest`. HTTP Basic auth (`email:token`). No Jinja2 (string templating). Local git only — never push.

**Spec:** `docs/specs/2026-05-22-jira-group-auditor-design.md`

**Conventions for every task:**
- All paths relative to `jira-group-auditor/`.
- Run tests from the project root with `python -m pytest`.
- Commits were made locally during the build (`git init` in Task 1); the finished tool was later published to a public GitHub repo (https://github.com/Ig0rmed3iros/Jira-c2c-group-eval).

---

## Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `config.example.toml`
- Create: `.gitignore`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Create dependency + config + ignore files**

`requirements.txt`:
```
requests==2.31.0
weasyprint==68.1
pytest==8.*
```

`config.example.toml`:
```toml
# Copy to config.toml (gitignored) and fill in. Token may instead come from the
# JIRA_API_TOKEN environment variable (preferred — keeps it out of files & shell history).
base_url = "https://your-instance.atlassian.net"
email = "you@example.com"
# token = "ATATT..."          # optional here; prefer JIRA_API_TOKEN env var
groups = ["jira-users"]
out_dir = "./reports"
```

`.gitignore`:
```
config.toml
__pycache__/
*.pyc
.pytest_cache/
*.pdf
*.json
!tests/fixtures/*.json
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 2: Create the smoke test**

`tests/__init__.py`: empty file.

`tests/test_smoke.py`:
```python
def test_python_runs():
    assert 1 + 1 == 2
```

- [ ] **Step 3: Run the smoke test**

Run: `cd jira-group-auditor && python -m pytest -q`
Expected: `1 passed`.

- [ ] **Step 4: Init local git + commit**

```bash
cd jira-group-auditor
git init
git add requirements.txt config.example.toml .gitignore pytest.ini tests/__init__.py tests/test_smoke.py docs/
git commit -m "chore: scaffold jira-group-auditor project"
```

---

## Task 2: Data model (`models.py`)

**Files:**
- Create: `models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
import json
from datetime import datetime, timezone
from models import (
    GroupAudit, Member, AppRoleRow, SchemeGrant, ProjectRef, audit_to_dict,
)


def _sample():
    a = GroupAudit(
        instance_host="x.atlassian.net",
        group_name="jira-users",
        group_id="gid-1",
        generated_at=datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc),
        generated_by="Igor Medeiros",
        members=[
            Member("Alice", "acc-1", True, "atlassian", "a@x.com"),
            Member("Bot", "acc-2", True, "app", None),
            Member("Old", "acc-3", False, "atlassian", None),
        ],
    )
    a.app_roles = [AppRoleRow("Jira Software", "jira-software", 255, 100000, False, False)]
    a.perm_schemes = [SchemeGrant(10009, "AC Permission Scheme", ["BROWSE_PROJECTS"], None, 146)]
    a.projects_by_scheme = {10009: [ProjectRef("A0", "Application Data")]}
    return a


def test_member_counts():
    a = _sample()
    assert a.member_total == 3
    assert a.active_count == 2
    assert a.inactive_count == 1


def test_audit_to_dict_is_json_serializable():
    a = _sample()
    d = audit_to_dict(a)
    s = json.dumps(d)  # must not raise
    assert '"jira-users"' in s
    # datetime serialized to ISO string
    assert d["generated_at"] == "2026-05-22T09:00:00+00:00"
    # int-keyed dict coerced to str keys for JSON
    assert d["projects_by_scheme"]["10009"][0]["key"] == "A0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'models'`.

- [ ] **Step 3: Write the implementation**

`models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from datetime import datetime
from typing import Any


@dataclass
class Member:
    display_name: str
    account_id: str
    active: bool
    account_type: str = "atlassian"   # atlassian | app | customer
    email: str | None = None


@dataclass
class AppRoleRow:
    name: str
    key: str
    seats_used: int | None
    seats_total: int | None
    is_member: bool
    is_default: bool


@dataclass
class ProjectRef:
    key: str
    name: str


@dataclass
class SchemeGrant:
    scheme_id: int
    scheme_name: str
    permissions: list[str]
    bundle_tag: str | None
    project_count: int


@dataclass
class SchemeMemberHit:
    scheme_id: int
    scheme_name: str
    detail: str


@dataclass
class RoleHit:
    role_id: int
    role_name: str
    is_default_actor: bool
    granted_by_any_scheme: bool


@dataclass
class FilterShare:
    filter_id: str
    name: str
    owner: str
    access: str   # "view" | "edit"


@dataclass
class JqlHit:
    filter_id: str
    name: str
    owner: str
    matched_clause: str


@dataclass
class DashboardShare:
    dashboard_id: str
    name: str
    owner: str
    access: str   # "view" | "edit"


@dataclass
class CustomFieldHit:
    field_id: str
    field_name: str
    context: str
    detail: str


@dataclass
class ManualCheck:
    dimension: str
    reason: str
    ui_path: str


@dataclass
class ExecutiveSummary:
    grants_license: bool
    headline: str
    elevated_powers: list[str] = field(default_factory=list)
    hygiene_flags: list[str] = field(default_factory=list)


@dataclass
class GroupAudit:
    instance_host: str
    group_name: str
    group_id: str
    generated_at: datetime
    generated_by: str

    members: list[Member] = field(default_factory=list)
    inactive_in_group: list[Member] = field(default_factory=list)
    non_human: list[Member] = field(default_factory=list)

    app_roles: list[AppRoleRow] = field(default_factory=list)
    grants_license: bool = False

    perm_schemes: list[SchemeGrant] = field(default_factory=list)
    projects_by_scheme: dict[int, list[ProjectRef]] = field(default_factory=dict)

    notification_hits: list[SchemeMemberHit] = field(default_factory=list)
    security_hits: list[SchemeMemberHit] = field(default_factory=list)
    role_hits: list[RoleHit] = field(default_factory=list)

    filters_shared: list[FilterShare] = field(default_factory=list)
    filters_jql: list[JqlHit] = field(default_factory=list)
    dashboards_shared: list[DashboardShare] = field(default_factory=list)
    custom_field_hits: list[CustomFieldHit] = field(default_factory=list)

    manual_checks: list[ManualCheck] = field(default_factory=list)
    incomplete_dimensions: list[str] = field(default_factory=list)

    summary: ExecutiveSummary | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def member_total(self) -> int:
        return len(self.members)

    @property
    def active_count(self) -> int:
        return sum(1 for m in self.members if m.active)

    @property
    def inactive_count(self) -> int:
        return sum(1 for m in self.members if not m.active)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def audit_to_dict(audit: GroupAudit) -> dict[str, Any]:
    """JSON-safe dict: datetimes -> ISO strings, int dict keys -> str."""
    return _jsonable(audit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: typed GroupAudit data model + JSON serialization"
```

---

## Task 3: JQL reference parser (`jql.py`)

The highest-risk unit. Only structured references count (membersOf / group operators / quoted exact name) — never bare substrings (guards against a project key resembling the group name).

**Files:**
- Create: `jql.py`
- Test: `tests/test_jql_parser.py`

- [ ] **Step 1: Write the failing test**

`tests/test_jql_parser.py`:
```python
from jql import find_group_references

NAME = "jira-users"
GID = "8bec6c67-2893-4e55-a124-16c250107f33"


def test_members_of_quoted():
    hits = find_group_references('assignee in membersOf("jira-users")', NAME, GID)
    assert hits == ['membersOf("jira-users")']


def test_members_of_unquoted():
    hits = find_group_references("reporter in membersOf(jira-users)", NAME, GID)
    assert hits == ["membersOf(jira-users)"]


def test_members_of_by_group_id():
    jql = f'watcher in membersOf("{GID}")'
    hits = find_group_references(jql, NAME, GID)
    assert hits == [f'membersOf("{GID}")']


def test_group_equals():
    hits = find_group_references('group = "jira-users" AND status = Open', NAME, GID)
    assert hits == ['group = "jira-users"']


def test_group_in_list():
    hits = find_group_references('group in ("admins", "jira-users")', NAME, GID)
    assert hits == ['group in ("admins", "jira-users")']


def test_case_insensitive_name():
    hits = find_group_references('membersOf("JIRA-USERS")', NAME, GID)
    assert hits == ['membersOf("JIRA-USERS")']


def test_no_match_for_other_group():
    assert find_group_references('membersOf("administrators")', NAME, GID) == []


def test_false_positive_project_key_guard():
    # a project/text that merely contains the group name must NOT match
    jql = 'project = "JIRA-USERS-PORTAL" AND text ~ "jira-users guide"'
    assert find_group_references(jql, NAME, GID) == []


def test_multiple_refs_deduped_in_order():
    jql = 'membersOf("jira-users") OR group = "jira-users"'
    hits = find_group_references(jql, NAME, GID)
    assert hits == ['membersOf("jira-users")', 'group = "jira-users"']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_jql_parser.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'jql'`.

- [ ] **Step 3: Write the implementation**

`jql.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_jql_parser.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add jql.py tests/test_jql_parser.py
git commit -m "feat: JQL group-reference parser with false-positive guard"
```

---

## Task 4: Group holder matcher (`matchers.py`)

**Files:**
- Create: `matchers.py`
- Test: `tests/test_matchers.py`

- [ ] **Step 1: Write the failing test**

`tests/test_matchers.py`:
```python
from matchers import holder_matches_group

NAME = "jira-users"
GID = "gid-1"


def test_match_by_parameter_name():
    h = {"type": "group", "parameter": "jira-users"}
    assert holder_matches_group(h, NAME, GID) is True


def test_match_by_value_group_id():
    h = {"type": "group", "value": "gid-1"}
    assert holder_matches_group(h, NAME, GID) is True


def test_match_by_nested_group_object():
    h = {"type": "group", "group": {"name": "jira-users", "groupId": "gid-1"}}
    assert holder_matches_group(h, NAME, GID) is True


def test_match_name_case_insensitive():
    h = {"type": "group", "parameter": "JIRA-USERS"}
    assert holder_matches_group(h, NAME, GID) is True


def test_no_match_other_group():
    h = {"type": "group", "parameter": "administrators", "value": "gid-9"}
    assert holder_matches_group(h, NAME, GID) is False


def test_no_match_non_group_holder():
    h = {"type": "projectRole", "parameter": "10037"}
    assert holder_matches_group(h, NAME, GID) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_matchers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'matchers'`.

- [ ] **Step 3: Write the implementation**

`matchers.py`:
```python
from __future__ import annotations


def holder_matches_group(holder: dict, group_name: str, group_id: str) -> bool:
    """True if a permission/notification/security holder targets the group.

    Handles all observed Cloud shapes:
      {"type":"group","parameter":"<name>","value":"<groupId>"}
      {"type":"group","group":{"name":..,"groupId":..}}   (expand=group)
    """
    if holder.get("type") != "group":
        return False
    grp = holder.get("group") or {}
    name = holder.get("parameter") or grp.get("name")
    gid = holder.get("value") or grp.get("groupId")
    if gid and gid == group_id:
        return True
    if name and name.casefold() == group_name.casefold():
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_matchers.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add matchers.py tests/test_matchers.py
git commit -m "feat: group holder matcher (name + groupId, all Cloud shapes)"
```

---

## Task 5: Classifiers & summary (`classify.py`)

**Files:**
- Create: `classify.py`
- Test: `tests/test_classify.py`

- [ ] **Step 1: Write the failing test**

`tests/test_classify.py`:
```python
from datetime import datetime, timezone
from models import (
    GroupAudit, Member, AppRoleRow, SchemeGrant, DashboardShare,
)
from classify import classify_bundle, is_non_human, derive_stats, build_summary


def test_classify_bundle_assignable():
    assert classify_bundle(["ASSIGNABLE_USER"]) == "broad assignee pool"


def test_classify_bundle_worklog():
    assert classify_bundle(["BROWSE_PROJECTS", "WORK_ON_ISSUES", "TRANSITION_ISSUES"]) == "worklog"


def test_classify_bundle_standard_is_none():
    assert classify_bundle(["BROWSE_PROJECTS", "ADD_COMMENTS"]) is None


def test_is_non_human_by_account_type():
    assert is_non_human(Member("Some App", "a", True, "app")) is True


def test_is_non_human_by_name():
    assert is_non_human(Member("JiraAPI", "a", True, "atlassian")) is True
    assert is_non_human(Member("Pentester One", "a", True, "atlassian")) is True
    assert is_non_human(Member("Alice Smith", "a", True, "atlassian")) is False


def _audit():
    a = GroupAudit("x.atlassian.net", "jira-users", "gid", datetime(2026, 5, 22, tzinfo=timezone.utc), "Igor")
    a.members = [Member("Alice", "1", True), Member("Old", "2", False), Member("JiraAPI", "3", True)]
    a.inactive_in_group = [Member("Old", "2", False)]
    a.non_human = [Member("JiraAPI", "3", True)]
    a.grants_license = False
    a.app_roles = [AppRoleRow("Jira Software", "jira-software", 255, 100000, False, False)]
    a.perm_schemes = [
        SchemeGrant(10009, "AC Permission Scheme", ["BROWSE_PROJECTS", "ADD_COMMENTS"], None, 146),
        SchemeGrant(10006, "MS Scheme", ["ASSIGNABLE_USER"], "broad assignee pool", 1),
    ]
    a.projects_by_scheme = {10009: [], 10006: []}
    a.dashboards_shared = [DashboardShare("10282", "DQI", "John", "edit")]
    return a


def test_derive_stats():
    s = derive_stats(_audit())
    assert s["members"] == 3
    assert s["active"] == 2
    assert s["inactive"] == 1
    assert s["permission_schemes"] == 2
    assert s["license_seats"] == 0


def test_build_summary_flags():
    summary = build_summary(_audit())
    assert summary.grants_license is False
    assert any("Assignable User" in p for p in summary.elevated_powers)
    assert any("inactive" in f.lower() for f in summary.hygiene_flags)
    assert any("edit" in f.lower() for f in summary.hygiene_flags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classify.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'classify'`.

- [ ] **Step 3: Write the implementation**

`classify.py`:
```python
from __future__ import annotations

import re

from models import GroupAudit, Member, ExecutiveSummary

_NON_HUMAN_RE = re.compile(
    r"(api|bot|svc|service|splunk|airflow|pentester|guest|administrator|"
    r"automation|jenkins|integration|test)\b",
    re.IGNORECASE,
)
_ELEVATED = {
    "ASSIGNABLE_USER": "Assignable User",
    "WORK_ON_ISSUES": "Work On Issues",
    "TRANSITION_ISSUES": "Transition Issues",
    "ADMINISTER_PROJECTS": "Administer Projects",
    "ADMINISTER": "Administer Jira",
}
_STANDARD = {
    "BROWSE_PROJECTS", "ADD_COMMENTS", "CREATE_ATTACHMENTS",
    "DELETE_OWN_ATTACHMENTS", "DELETE_OWN_COMMENTS", "EDIT_OWN_COMMENTS",
    "VIEW_READONLY_WORKFLOW", "VIEW_VOTERS_AND_WATCHERS",
}


def classify_bundle(permissions: list[str]) -> str | None:
    perms = set(permissions)
    if "ASSIGNABLE_USER" in perms:
        return "broad assignee pool"
    if perms & {"WORK_ON_ISSUES", "TRANSITION_ISSUES"}:
        return "worklog"
    return None


def is_non_human(member: Member) -> bool:
    if member.account_type == "app":
        return True
    return bool(_NON_HUMAN_RE.search(member.display_name or ""))


def derive_stats(audit: GroupAudit) -> dict[str, int]:
    seats = sum(r.seats_used or 0 for r in audit.app_roles if r.is_member or r.is_default)
    projects = len({p.key for refs in audit.projects_by_scheme.values() for p in refs})
    return {
        "members": audit.member_total,
        "active": audit.active_count,
        "inactive": audit.inactive_count,
        "permission_schemes": len(audit.perm_schemes),
        "projects_affected": projects,
        "filters_shared": len(audit.filters_shared),
        "dashboards_shared": len(audit.dashboards_shared),
        "jql_references": len(audit.filters_jql),
        "custom_field_refs": len(audit.custom_field_hits),
        "license_seats": seats,
    }


def build_summary(audit: GroupAudit) -> ExecutiveSummary:
    if audit.grants_license:
        headline = (
            f"Grants a license seat. {audit.group_name} is a member or default group on at "
            f"least one application role, so adding/removing members affects seats."
        )
    else:
        headline = (
            f"Grants no license. {audit.group_name} is neither a member nor a default group on "
            f"any application role — it is a pure permission & visibility bucket."
        )

    elevated: list[str] = []
    for scheme in audit.perm_schemes:
        for perm in scheme.permissions:
            label = _ELEVATED.get(perm)
            if label:
                elevated.append(f"{label} via {scheme.scheme_name} ({scheme.project_count} project(s))")

    flags: list[str] = []
    if audit.inactive_in_group:
        flags.append(f"{len(audit.inactive_in_group)} inactive account(s) still in the group")
    if audit.non_human:
        flags.append(f"{len(audit.non_human)} bot/service/test account(s) present")
    edit_dashboards = [d for d in audit.dashboards_shared if d.access == "edit"]
    if edit_dashboards:
        flags.append(f"{len(edit_dashboards)} dashboard(s) shared with EDIT to all members")
    assignee_schemes = [s for s in audit.perm_schemes if s.bundle_tag == "broad assignee pool"]
    if assignee_schemes:
        flags.append(f"entire group is the assignable pool on {len(assignee_schemes)} scheme(s)")

    return ExecutiveSummary(
        grants_license=audit.grants_license,
        headline=headline,
        elevated_powers=elevated,
        hygiene_flags=flags,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_classify.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add classify.py tests/test_classify.py
git commit -m "feat: bundle classifier, bot heuristic, stats + exec-summary derivation"
```

---

## Task 6: Jira REST client (`jira_client.py`)

**Files:**
- Create: `jira_client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

`tests/test_client.py`:
```python
import pytest
from jira_client import JiraClient


class FakeResp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.auth = None
        self.headers = {}

    def get(self, url, params=None):
        self.calls.append((url, params))
        return self._responses.pop(0)


def _client(session):
    return JiraClient("https://x.atlassian.net", "e@x.com", "tok", session=session)


def test_get_returns_json():
    c = _client(FakeSession([FakeResp(200, {"ok": True})]))
    assert c.get("/rest/api/3/myself") == {"ok": True}


def test_get_retries_on_429(monkeypatch):
    monkeypatch.setattr("jira_client.time.sleep", lambda *_: None)
    session = FakeSession([FakeResp(429, headers={"Retry-After": "0"}), FakeResp(200, {"ok": 1})])
    c = _client(session)
    assert c.get("/x") == {"ok": 1}
    assert len(session.calls) == 2


def test_paginate_offset_two_pages():
    page1 = FakeResp(200, {"values": [{"id": 1}] * 100, "isLast": False})
    page2 = FakeResp(200, {"values": [{"id": 2}], "isLast": True})
    c = _client(FakeSession([page1, page2]))
    out = c.paginate("/rest/api/3/filter/search")
    assert len(out) == 101


def test_paginate_custom_values_key():
    page = FakeResp(200, {"dashboards": [{"id": "d1"}], "isLast": True})
    c = _client(FakeSession([page]))
    out = c.paginate("/rest/api/3/dashboard/search", values_key="dashboards")
    assert out == [{"id": "d1"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'jira_client'`.

- [ ] **Step 3: Write the implementation**

`jira_client.py`:
```python
from __future__ import annotations

import time

import requests


class JiraClient:
    def __init__(self, base_url: str, email: str, token: str, session=None, max_retries: int = 5):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.auth = (email, token)
        self.session.headers.update({"Accept": "application/json"})
        self.max_retries = max_retries

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.base_url}{path}"

    def get(self, path: str, params: dict | None = None) -> dict:
        last = None
        for attempt in range(self.max_retries):
            resp = self.session.get(self._url(path), params=params)
            last = resp
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        last.raise_for_status()
        raise RuntimeError("unreachable")

    def verify_auth(self) -> dict:
        return self.get("/rest/api/3/myself")

    def paginate(self, path: str, params: dict | None = None, values_key: str = "values") -> list:
        params = dict(params or {})
        page = 100
        params["maxResults"] = page
        start = 0
        out: list = []
        while True:
            params["startAt"] = start
            data = self.get(path, params)
            vals = data.get(values_key, [])
            out.extend(vals)
            if data.get("isLast") is True:
                break
            if len(vals) < page:
                break
            start += page
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add jira_client.py tests/test_client.py
git commit -m "feat: Jira Cloud REST client with 429 backoff + offset pagination"
```

---

## Task 7: Collectors — membership + application access (`sweep.py`)

**Files:**
- Create: `sweep.py`
- Test: `tests/test_sweep_membership.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sweep_membership.py`:
```python
from sweep import resolve_group, collect_app_access
from models import Member


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}

    def get(self, path, params=None):
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map[path]


def test_resolve_group_returns_id_and_members():
    client = StubClient(
        get_map={"/rest/api/3/group/bulk": {"values": [{"name": "jira-users", "groupId": "gid-1"}]}},
        paginate_map={"/rest/api/3/group/member": [
            {"accountId": "1", "displayName": "Alice", "active": True, "accountType": "atlassian", "emailAddress": "a@x.com"},
            {"accountId": "2", "displayName": "Old", "active": False, "accountType": "atlassian"},
        ]},
    )
    gid, members = resolve_group(client, "jira-users")
    assert gid == "gid-1"
    assert members[0] == Member("Alice", "1", True, "atlassian", "a@x.com")
    assert members[1].active is False


def test_collect_app_access_no_membership_means_no_license():
    client = StubClient(get_map={"/rest/api/3/applicationrole": [
        {"key": "jira-software", "name": "Jira Software", "groups": ["jira-software-users"],
         "defaultGroups": [], "userCount": 255, "numberOfSeats": 100000,
         "groupDetails": [{"name": "jira-software-users", "groupId": "gid-x"}],
         "defaultGroupsDetails": []},
    ]})
    rows, grants = collect_app_access(client, "jira-users", "gid-1")
    assert grants is False
    assert rows[0].seats_used == 255 and rows[0].seats_total == 100000
    assert rows[0].is_member is False


def test_collect_app_access_membership_grants_license():
    client = StubClient(get_map={"/rest/api/3/applicationrole": [
        {"key": "jira-software", "name": "Jira Software", "groups": ["jira-users"],
         "defaultGroups": [], "userCount": 10, "numberOfSeats": 100,
         "groupDetails": [{"name": "jira-users", "groupId": "gid-1"}], "defaultGroupsDetails": []},
    ]})
    rows, grants = collect_app_access(client, "jira-users", "gid-1")
    assert grants is True
    assert rows[0].is_member is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sweep_membership.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sweep'`.

- [ ] **Step 3: Write the implementation**

`sweep.py`:
```python
from __future__ import annotations

from models import AppRoleRow, Member


def resolve_group(client, group_name: str) -> tuple[str, list[Member]]:
    data = client.get("/rest/api/3/group/bulk", params={"groupName": group_name})
    matches = data.get("values", [])
    if not matches:
        try:
            picker = client.get("/rest/api/3/groups/picker", params={"query": group_name})
            suggestions = ", ".join(g.get("name", "") for g in picker.get("groups", [])[:8])
        except Exception:  # noqa: BLE001
            suggestions = ""
        hint = f" Did you mean: {suggestions}?" if suggestions else ""
        raise LookupError(f"group not found: {group_name}.{hint}")
    group_id = matches[0]["groupId"]
    raw = client.paginate(
        "/rest/api/3/group/member",
        params={"groupId": group_id, "includeInactiveUsers": "true"},
    )
    members = [
        Member(
            display_name=u.get("displayName", ""),
            account_id=u.get("accountId", ""),
            active=bool(u.get("active", False)),
            account_type=u.get("accountType", "atlassian"),
            email=u.get("emailAddress"),
        )
        for u in raw
    ]
    return group_id, members


def collect_app_access(client, group_name: str, group_id: str) -> tuple[list[AppRoleRow], bool]:
    roles_raw = client.get("/rest/api/3/applicationrole")
    name_cf = group_name.casefold()
    rows: list[AppRoleRow] = []
    grants = False
    for r in roles_raw:
        member_names = {g.casefold() for g in r.get("groups", [])}
        member_ids = {d.get("groupId") for d in r.get("groupDetails", [])}
        default_names = {g.casefold() for g in r.get("defaultGroups", [])}
        default_ids = {d.get("groupId") for d in r.get("defaultGroupsDetails", [])}
        is_member = name_cf in member_names or group_id in member_ids
        is_default = name_cf in default_names or group_id in default_ids
        grants = grants or is_member or is_default
        rows.append(AppRoleRow(
            name=r.get("name", ""),
            key=r.get("key", ""),
            seats_used=r.get("userCount"),
            seats_total=r.get("numberOfSeats"),
            is_member=is_member,
            is_default=is_default,
        ))
    return rows, grants
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sweep_membership.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add sweep.py tests/test_sweep_membership.py
git commit -m "feat: collectors for group membership + application access"
```

---

## Task 8: Collectors — permission schemes + projects-by-scheme

**Files:**
- Modify: `sweep.py` (append functions)
- Test: `tests/test_sweep_permissions.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sweep_permissions.py`:
```python
from sweep import collect_permission_schemes


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map[path]


SCHEMES = {
    "permissionSchemes": [
        {"id": 10009, "name": "AC Permission Scheme", "permissions": [
            {"permission": "BROWSE_PROJECTS", "holder": {"type": "group", "parameter": "jira-users"}},
            {"permission": "ADD_COMMENTS", "holder": {"type": "group", "parameter": "jira-users"}},
        ]},
        {"id": 10006, "name": "MS Scheme", "permissions": [
            {"permission": "ASSIGNABLE_USER", "holder": {"type": "group", "value": "gid-1"}},
        ]},
        {"id": 99999, "name": "Unrelated", "permissions": [
            {"permission": "BROWSE_PROJECTS", "holder": {"type": "group", "parameter": "other"}},
        ]},
    ]
}


def _client():
    return StubClient(
        get_map={
            "/rest/api/3/project/AC1/permissionscheme": {"id": 10009},
            "/rest/api/3/project/MS1/permissionscheme": {"id": 10006},
        },
        paginate_map={"/rest/api/3/project/search": [
            {"key": "AC1", "name": "AC One"},
            {"key": "MS1", "name": "Managed Services"},
        ]},
    )


def test_collect_permission_schemes_matches_and_counts():
    client = _client()
    schemes, projects_by_scheme = collect_permission_schemes(client, "jira-users", "gid-1", SCHEMES)
    ids = {s.scheme_id for s in schemes}
    assert ids == {10009, 10006}            # unrelated scheme excluded
    by_id = {s.scheme_id: s for s in schemes}
    assert set(by_id[10009].permissions) == {"BROWSE_PROJECTS", "ADD_COMMENTS"}
    assert by_id[10009].bundle_tag is None
    assert by_id[10006].bundle_tag == "broad assignee pool"
    assert by_id[10009].project_count == 1
    assert projects_by_scheme[10009][0].key == "AC1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sweep_permissions.py -q`
Expected: FAIL with `ImportError: cannot import name 'collect_permission_schemes'`.

- [ ] **Step 3: Write the implementation (append to `sweep.py`)**

Add this import at the top of `sweep.py` (extend the existing import line):
```python
from models import AppRoleRow, Member, ProjectRef, SchemeGrant
from matchers import holder_matches_group
from classify import classify_bundle
```

Append:
```python
def fetch_permission_schemes(client) -> dict:
    """Single fetch shared by permission-scheme and project-role collectors."""
    return client.get("/rest/api/3/permissionscheme", params={"expand": "permissions,group"})


def collect_permission_schemes(
    client, group_name: str, group_id: str, schemes_payload: dict
) -> tuple[list[SchemeGrant], dict[int, list[ProjectRef]]]:
    matched: dict[int, dict] = {}
    for scheme in schemes_payload.get("permissionSchemes", []):
        perms = sorted({
            p["permission"]
            for p in scheme.get("permissions", [])
            if holder_matches_group(p.get("holder", {}), group_name, group_id)
        })
        if perms:
            matched[scheme["id"]] = {"name": scheme.get("name", ""), "permissions": perms}

    projects_by_scheme: dict[int, list[ProjectRef]] = {sid: [] for sid in matched}
    for proj in client.paginate("/rest/api/3/project/search"):
        key = proj["key"]
        assoc = client.get(f"/rest/api/3/project/{key}/permissionscheme")
        sid = assoc.get("id")
        if sid in projects_by_scheme:
            projects_by_scheme[sid].append(ProjectRef(key=key, name=proj.get("name", "")))

    grants = [
        SchemeGrant(
            scheme_id=sid,
            scheme_name=info["name"],
            permissions=info["permissions"],
            bundle_tag=classify_bundle(info["permissions"]),
            project_count=len(projects_by_scheme[sid]),
        )
        for sid, info in matched.items()
    ]
    grants.sort(key=lambda g: g.scheme_id)
    return grants, projects_by_scheme
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sweep_permissions.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add sweep.py tests/test_sweep_permissions.py
git commit -m "feat: permission-scheme collector with projects-by-scheme mapping"
```

---

## Task 9: Collectors — notification, issue security, project roles

**Files:**
- Modify: `sweep.py` (append)
- Test: `tests/test_sweep_other.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sweep_other.py`:
```python
from sweep import collect_notification_schemes, collect_security_schemes, collect_project_roles


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}

    def get(self, path, params=None):
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map.get(path, [])


def test_notification_hit():
    client = StubClient(paginate_map={"/rest/api/3/notificationscheme": [
        {"id": 1, "name": "Default", "notificationSchemeEvents": [
            {"event": {"name": "Issue Created"},
             "notifications": [{"notificationType": "Group", "type": "group", "parameter": "jira-users"}]},
        ]},
    ]})
    hits = collect_notification_schemes(client, "jira-users", "gid-1")
    assert len(hits) == 1 and hits[0].scheme_id == 1


def test_security_no_hit():
    client = StubClient(
        get_map={"/rest/api/3/issuesecurityschemes": {"issueSecuritySchemes": [{"id": 7, "name": "Sec"}]}},
        paginate_map={"/rest/api/3/issuesecurityschemes/level/member": [
            {"holder": {"type": "group", "parameter": "other"}},
        ]},
    )
    hits = collect_security_schemes(client, "jira-users", "gid-1")
    assert hits == []


def test_project_role_inert_artifact():
    client = StubClient(get_map={"/rest/api/3/role": [
        {"id": 10037, "name": "JIRA Users (migrated 2)",
         "actors": [{"type": "atlassian-group-role-actor", "name": "jira-users",
                     "actorGroup": {"name": "jira-users", "groupId": "gid-1"}}]},
    ]})
    # no scheme grants to role 10037 -> inert
    hits = collect_project_roles(client, "jira-users", "gid-1", granted_role_ids=set())
    assert len(hits) == 1
    assert hits[0].is_default_actor is True
    assert hits[0].granted_by_any_scheme is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sweep_other.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write the implementation (append to `sweep.py`)**

Extend the model import line to add `RoleHit, SchemeMemberHit`:
```python
from models import AppRoleRow, Member, ProjectRef, SchemeGrant, RoleHit, SchemeMemberHit
```

Append:
```python
def collect_notification_schemes(client, group_name: str, group_id: str) -> list[SchemeMemberHit]:
    hits: list[SchemeMemberHit] = []
    for scheme in client.paginate("/rest/api/3/notificationscheme", params={"expand": "all"}):
        events = []
        for ev in scheme.get("notificationSchemeEvents", []):
            for n in ev.get("notifications", []):
                if holder_matches_group(n, group_name, group_id):
                    events.append(ev.get("event", {}).get("name", "event"))
        if events:
            hits.append(SchemeMemberHit(scheme["id"], scheme.get("name", ""), ", ".join(sorted(set(events)))))
    return hits


def collect_security_schemes(client, group_name: str, group_id: str) -> list[SchemeMemberHit]:
    schemes = client.get("/rest/api/3/issuesecurityschemes").get("issueSecuritySchemes", [])
    hits: list[SchemeMemberHit] = []
    for scheme in schemes:
        members = client.paginate(
            "/rest/api/3/issuesecurityschemes/level/member",
            params={"schemeId": scheme["id"]},
        )
        if any(holder_matches_group(m.get("holder", {}), group_name, group_id) for m in members):
            hits.append(SchemeMemberHit(scheme["id"], scheme.get("name", ""), "member of a security level"))
    return hits


def collect_project_roles(client, group_name: str, group_id: str, granted_role_ids: set[int]) -> list[RoleHit]:
    hits: list[RoleHit] = []
    name_cf = group_name.casefold()
    for role in client.get("/rest/api/3/role"):
        is_default_actor = False
        for actor in role.get("actors", []):
            ag = actor.get("actorGroup") or {}
            if ag.get("groupId") == group_id or (actor.get("name", "").casefold() == name_cf):
                is_default_actor = True
                break
        if is_default_actor:
            hits.append(RoleHit(
                role_id=role["id"],
                role_name=role.get("name", ""),
                is_default_actor=True,
                granted_by_any_scheme=role["id"] in granted_role_ids,
            ))
    return hits


def granted_role_ids_from_schemes(schemes_payload: dict) -> set[int]:
    ids: set[int] = set()
    for scheme in schemes_payload.get("permissionSchemes", []):
        for p in scheme.get("permissions", []):
            holder = p.get("holder", {})
            if holder.get("type") == "projectRole":
                try:
                    ids.add(int(holder.get("parameter") or holder.get("value")))
                except (TypeError, ValueError):
                    pass
    return ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sweep_other.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add sweep.py tests/test_sweep_other.py
git commit -m "feat: notification, issue-security, project-role collectors"
```

---

## Task 10: Collectors — filters (shared + JQL), dashboards, boards

**Files:**
- Modify: `sweep.py` (append)
- Test: `tests/test_sweep_filters.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sweep_filters.py`:
```python
from sweep import collect_filters, collect_dashboards, collect_boards


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}

    def get(self, path, params=None):
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map.get(path, [])


def test_collect_filters_share_and_jql():
    client = StubClient(paginate_map={"/rest/api/3/filter/search": [
        {"id": "100", "name": "Shared View", "owner": {"displayName": "Hugo"},
         "jql": "project = AC", "sharePermissions": [{"type": "group", "group": {"name": "jira-users", "groupId": "gid-1"}}],
         "editPermissions": []},
        {"id": "200", "name": "JQL Ref", "owner": {"displayName": "Igor"},
         "jql": 'assignee in membersOf("jira-users")', "sharePermissions": [], "editPermissions": []},
        {"id": "300", "name": "Unrelated", "owner": {"displayName": "Bob"},
         "jql": "project = X", "sharePermissions": [], "editPermissions": []},
    ]})
    shared, jql_hits = collect_filters(client, "jira-users", "gid-1")
    assert [s.filter_id for s in shared] == ["100"]
    assert shared[0].access == "view"
    assert [j.filter_id for j in jql_hits] == ["200"]
    assert jql_hits[0].matched_clause == 'membersOf("jira-users")'


def test_collect_dashboards_edit_flag():
    client = StubClient(paginate_map={"/rest/api/3/dashboard/search": [
        {"id": "d1", "name": "DQI", "owner": {"displayName": "John"},
         "sharePermissions": [], "editPermissions": [{"type": "group", "group": {"name": "jira-users", "groupId": "gid-1"}}]},
    ]})
    shared = collect_dashboards(client, "jira-users", "gid-1")
    assert shared[0].access == "edit"


def test_collect_boards_backing_filter_jql():
    client = StubClient(
        paginate_map={"/rest/agile/1.0/board": [{"id": 5, "name": "ACL Board"}]},
        get_map={
            "/rest/agile/1.0/board/5/configuration": {"filter": {"id": "900"}},
            "/rest/api/3/filter/900": {"id": "900", "name": "ACL Board", "owner": {"displayName": "Richard"},
                                       "jql": 'group = "jira-users"'},
        },
    )
    jql_hits = collect_boards(client, "jira-users", "gid-1", already_seen_filter_ids={"200"})
    assert jql_hits[0].filter_id == "900"
    assert jql_hits[0].matched_clause == 'group = "jira-users"'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sweep_filters.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write the implementation (append to `sweep.py`)**

Extend the model import to add `FilterShare, JqlHit, DashboardShare`, and add the jql import:
```python
from models import (
    AppRoleRow, Member, ProjectRef, SchemeGrant, RoleHit, SchemeMemberHit,
    FilterShare, JqlHit, DashboardShare,
)
from jql import find_group_references
```

Append:
```python
def _owner_name(obj: dict) -> str:
    return (obj.get("owner") or {}).get("displayName", "")


def _shares_match(perms: list[dict], group_name: str, group_id: str) -> bool:
    return any(holder_matches_group(p, group_name, group_id) for p in perms or [])


def collect_filters(client, group_name: str, group_id: str) -> tuple[list[FilterShare], list[JqlHit]]:
    shared: list[FilterShare] = []
    jql_hits: list[JqlHit] = []
    raw = client.paginate(
        "/rest/api/3/filter/search",
        params={"expand": "jql,sharePermissions,editPermissions,owner"},
    )
    for f in raw:
        fid, name, owner = f["id"], f.get("name", ""), _owner_name(f)
        if _shares_match(f.get("editPermissions"), group_name, group_id):
            shared.append(FilterShare(fid, name, owner, "edit"))
        elif _shares_match(f.get("sharePermissions"), group_name, group_id):
            shared.append(FilterShare(fid, name, owner, "view"))
        refs = find_group_references(f.get("jql", ""), group_name, group_id)
        if refs:
            jql_hits.append(JqlHit(fid, name, owner, "; ".join(refs)))
    return shared, jql_hits


def collect_dashboards(client, group_name: str, group_id: str) -> list[DashboardShare]:
    shared: list[DashboardShare] = []
    raw = client.paginate(
        "/rest/api/3/dashboard/search",
        params={"expand": "sharePermissions,editPermissions"},
        values_key="dashboards",
    )
    for d in raw:
        did, name, owner = d["id"], d.get("name", ""), _owner_name(d)
        if _shares_match(d.get("editPermissions"), group_name, group_id):
            shared.append(DashboardShare(did, name, owner, "edit"))
        elif _shares_match(d.get("sharePermissions"), group_name, group_id):
            shared.append(DashboardShare(did, name, owner, "view"))
    return shared


def collect_boards(client, group_name: str, group_id: str, already_seen_filter_ids: set[str]) -> list[JqlHit]:
    hits: list[JqlHit] = []
    for board in client.paginate("/rest/agile/1.0/board"):
        config = client.get(f"/rest/agile/1.0/board/{board['id']}/configuration")
        filter_id = str((config.get("filter") or {}).get("id", ""))
        if not filter_id or filter_id in already_seen_filter_ids:
            continue
        already_seen_filter_ids.add(filter_id)
        f = client.get(f"/rest/api/3/filter/{filter_id}")
        refs = find_group_references(f.get("jql", ""), group_name, group_id)
        if refs:
            hits.append(JqlHit(filter_id, f.get("name", board.get("name", "")), _owner_name(f), "; ".join(refs)))
    return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sweep_filters.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add sweep.py tests/test_sweep_filters.py
git commit -m "feat: filter (share+JQL), dashboard, and board collectors"
```

---

## Task 11: Collectors — custom fields, manual checks, and `collect()` orchestration

**Files:**
- Modify: `sweep.py` (append)
- Test: `tests/test_sweep_collect.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sweep_collect.py`:
```python
from datetime import datetime, timezone
import sweep
from models import GroupAudit, Member


def test_collect_custom_fields_group_picker():
    class Stub:
        def get(self, path, params=None):
            if path == "/rest/api/3/field":
                return [{"id": "customfield_1", "name": "Approver Group",
                         "schema": {"custom": "com.atlassian.jira.plugin.system.customfieldtypes:grouppicker"}}]
            raise KeyError(path)

        def paginate(self, path, params=None, values_key="values"):
            if path == "/rest/api/3/field/customfield_1/context":
                return [{"id": "ctx-1", "name": "Default Context"}]
            if path == "/rest/api/3/field/customfield_1/context/defaultValue":
                return [{"contextId": "ctx-1", "type": "group", "groupId": "gid-1"}]
            return []

    hits = sweep.collect_custom_fields(Stub(), "jira-users", "gid-1")
    assert len(hits) == 1 and hits[0].field_id == "customfield_1"


def test_default_manual_checks_listed():
    checks = sweep.default_manual_checks()
    dims = {c.dimension for c in checks}
    assert "Global permissions" in dims
    assert "Automation rules" in dims


def test_collect_isolates_failing_dimension(monkeypatch):
    # resolve_group + verify succeed; one collector raises -> recorded, run continues
    monkeypatch.setattr(sweep, "resolve_group", lambda c, n: ("gid-1", [Member("Alice", "1", True)]))
    monkeypatch.setattr(sweep, "collect_app_access", lambda c, n, g: ([], False))
    monkeypatch.setattr(sweep, "fetch_permission_schemes", lambda c: {"permissionSchemes": []})
    monkeypatch.setattr(sweep, "collect_permission_schemes", lambda *a: ([], {}))
    monkeypatch.setattr(sweep, "granted_role_ids_from_schemes", lambda p: set())
    monkeypatch.setattr(sweep, "collect_project_roles", lambda *a, **k: [])
    monkeypatch.setattr(sweep, "collect_notification_schemes", lambda *a: [])
    monkeypatch.setattr(sweep, "collect_security_schemes", lambda *a: [])
    def boom(*a, **k):
        raise RuntimeError("403")
    monkeypatch.setattr(sweep, "collect_filters", boom)            # this one fails
    monkeypatch.setattr(sweep, "collect_dashboards", lambda *a: [])
    monkeypatch.setattr(sweep, "collect_boards", lambda *a, **k: [])
    monkeypatch.setattr(sweep, "collect_custom_fields", lambda *a: [])

    class Stub:
        base_url = "https://acme.atlassian.net"
        def verify_auth(self):
            return {"displayName": "Igor"}

    audit = sweep.collect(Stub(), "jira-users")
    assert isinstance(audit, GroupAudit)
    assert audit.group_id == "gid-1"
    assert "filters" in audit.incomplete_dimensions
    assert audit.summary is not None and audit.stats["members"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sweep_collect.py -q`
Expected: FAIL with `AttributeError`/`ImportError`.

- [ ] **Step 3: Write the implementation (append to `sweep.py`)**

Extend imports at the top of `sweep.py`:
```python
from datetime import datetime, timezone
from urllib.parse import urlparse

from models import (
    AppRoleRow, Member, ProjectRef, SchemeGrant, RoleHit, SchemeMemberHit,
    FilterShare, JqlHit, DashboardShare, CustomFieldHit, ManualCheck, GroupAudit,
)
from classify import classify_bundle, is_non_human, derive_stats, build_summary
```

Append:
```python
_GROUP_PICKER_TYPES = {
    "com.atlassian.jira.plugin.system.customfieldtypes:grouppicker",
    "com.atlassian.jira.plugin.system.customfieldtypes:multigrouppicker",
}


def collect_custom_fields(client, group_name: str, group_id: str) -> list[CustomFieldHit]:
    hits: list[CustomFieldHit] = []
    name_cf = group_name.casefold()
    for field in client.get("/rest/api/3/field"):
        if field.get("schema", {}).get("custom") not in _GROUP_PICKER_TYPES:
            continue
        fid, fname = field["id"], field.get("name", "")
        contexts = {c["id"]: c.get("name", c["id"]) for c in client.paginate(f"/rest/api/3/field/{fid}/context")}
        for dv in client.paginate(f"/rest/api/3/field/{fid}/context/defaultValue"):
            gids = {dv.get("groupId")} | {g.get("groupId") for g in dv.get("groups", [])}
            gnames = {dv.get("groupName", "").casefold()} | {g.get("name", "").casefold() for g in dv.get("groups", [])}
            if group_id in gids or name_cf in gnames:
                ctx = contexts.get(dv.get("contextId"), str(dv.get("contextId")))
                hits.append(CustomFieldHit(fid, fname, ctx, "default value references the group"))
    return hits


def default_manual_checks() -> list[ManualCheck]:
    return [
        ManualCheck("Global permissions",
                    "No public Cloud REST read endpoint (Browse users & groups, Bulk change, Share objects, etc.)",
                    "Settings > System > Global permissions"),
        ManualCheck("Automation rules",
                    "Group conditions/actions are not exposed over public REST",
                    "Project / Global automation"),
        ManualCheck("Workflow conditions & validators",
                    "Group-based transition restrictions are not reliably readable over REST",
                    "Workflow editor > transition conditions/validators"),
        ManualCheck("Dashboard gadget JQL",
                    "Raw JQL inside individual gadgets is not enumerated",
                    "Open each shared dashboard's gadget configuration"),
    ]


def _host(base_url: str) -> str:
    return urlparse(base_url).netloc


def _guard(audit: GroupAudit, dimension: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - intentional per-dimension isolation
        audit.incomplete_dimensions.append(dimension)
        audit.manual_checks.append(
            ManualCheck(dimension, f"REST error during sweep: {exc}", "verify manually in the UI")
        )


def collect(client, group_name: str) -> GroupAudit:
    me = client.verify_auth()
    group_id, members = resolve_group(client, group_name)
    audit = GroupAudit(
        instance_host=_host(client.base_url),
        group_name=group_name,
        group_id=group_id,
        generated_at=datetime.now(timezone.utc),
        generated_by=me.get("displayName", ""),
        members=members,
    )
    audit.inactive_in_group = [m for m in members if not m.active]
    audit.non_human = [m for m in members if is_non_human(m)]

    def _app():
        audit.app_roles, audit.grants_license = collect_app_access(client, group_name, group_id)
    _guard(audit, "application access", _app)

    schemes_payload: dict = {"permissionSchemes": []}

    def _schemes():
        nonlocal schemes_payload
        schemes_payload = fetch_permission_schemes(client)
        audit.perm_schemes, audit.projects_by_scheme = collect_permission_schemes(
            client, group_name, group_id, schemes_payload
        )
    _guard(audit, "permission schemes", _schemes)

    def _roles():
        granted = granted_role_ids_from_schemes(schemes_payload)
        audit.role_hits = collect_project_roles(client, group_name, group_id, granted)
    _guard(audit, "project roles", _roles)

    _guard(audit, "notification schemes",
           lambda: audit.notification_hits.extend(collect_notification_schemes(client, group_name, group_id)))
    _guard(audit, "issue security schemes",
           lambda: audit.security_hits.extend(collect_security_schemes(client, group_name, group_id)))

    seen_filter_ids: set[str] = set()

    def _filters():
        shared, jql_hits = collect_filters(client, group_name, group_id)
        audit.filters_shared.extend(shared)
        audit.filters_jql.extend(jql_hits)
        seen_filter_ids.update(j.filter_id for j in jql_hits)
    _guard(audit, "filters", _filters)

    _guard(audit, "dashboards",
           lambda: audit.dashboards_shared.extend(collect_dashboards(client, group_name, group_id)))
    _guard(audit, "boards",
           lambda: audit.filters_jql.extend(collect_boards(client, group_name, group_id, seen_filter_ids)))
    _guard(audit, "custom fields",
           lambda: audit.custom_field_hits.extend(collect_custom_fields(client, group_name, group_id)))

    audit.manual_checks.extend(default_manual_checks())
    audit.stats = derive_stats(audit)
    audit.summary = build_summary(audit)
    return audit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sweep_collect.py -q`
Expected: `3 passed`. Then run the full suite: `python -m pytest -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add sweep.py tests/test_sweep_collect.py
git commit -m "feat: custom-field collector, manual-check section, collect() orchestration"
```

---

## Task 12: Report assets (`report_assets.py`)

**Files:**
- Create: `report_assets.py`
- Test: `tests/test_report_assets.py`

- [ ] **Step 1: Write the failing test**

`tests/test_report_assets.py`:
```python
from report_assets import CSS, html_escape, stat_card, section_table, badge


def test_css_has_page_footer_and_header():
    assert "@page" in CSS
    assert "counter(page)" in CSS
    assert ".header" in CSS


def test_html_escape():
    assert html_escape('a & "b" <c>') == "a &amp; &quot;b&quot; &lt;c&gt;"


def test_stat_card_renders_value_and_label():
    out = stat_card(195, "TOTAL MEMBERS")
    assert "195" in out and "TOTAL MEMBERS" in out


def test_section_table_headers_and_rows():
    out = section_table(["A", "B"], [["1", "2"], ["3", "4"]])
    assert "<th>A</th>" in out
    assert "<td>3</td>" in out


def test_badge_variants():
    assert "badge-edit" in badge("EDIT", "edit")
    assert "badge-view" in badge("view", "view")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report_assets.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`report_assets.py`:
```python
from __future__ import annotations

CSS = """
@page {
  size: A4; margin: 1.6cm 1.4cm 2cm 1.4cm;
  @bottom-left { content: "Jira Group Auditor — " string(doctitle); font-size: 8pt; color: #9aa5b1; }
  @bottom-right { content: "Page " counter(page) " / " counter(pages); font-size: 8pt; color: #9aa5b1; }
}
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1f2933; font-size: 10.5pt; }
h1 { string-set: doctitle content(); }
.header { background: linear-gradient(135deg, #1c3d6e, #2a5298); color: #fff; padding: 22px 24px; border-radius: 8px; }
.header h1 { margin: 0 0 6px; font-size: 24pt; }
.header .sub { font-size: 11pt; opacity: 0.95; }
.header .meta { font-size: 8.5pt; opacity: 0.85; margin-top: 10px; }
.cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
.card { flex: 1 1 30%; border: 1px solid #e4e7eb; border-radius: 8px; padding: 12px 14px; }
.card .value { font-size: 22pt; font-weight: 700; color: #2a5298; }
.card .label { font-size: 8pt; letter-spacing: 0.04em; color: #7b8794; text-transform: uppercase; }
h2 { font-size: 14pt; border-bottom: 2px solid #2a5298; padding-bottom: 4px; margin-top: 26px; }
.callout { border-left: 4px solid #2a5298; background: #f5f7fa; padding: 10px 14px; margin: 8px 0; font-size: 10pt; }
.callout.warn { border-left-color: #de911d; background: #fdf6e3; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9pt; }
th { background: #1f2933; color: #fff; text-align: left; padding: 6px 8px; }
td { border-bottom: 1px solid #eceff1; padding: 5px 8px; vertical-align: top; }
.pill { display: inline-block; background: #eef2f7; border: 1px solid #d2dae6; border-radius: 10px; padding: 1px 8px; margin: 1px; font-size: 8pt; }
.tag { display: inline-block; background: #fdf0d5; color: #8a6d1b; border-radius: 4px; padding: 1px 6px; font-size: 8pt; }
.badge-view { background: #e6f0ff; color: #2a5298; border-radius: 4px; padding: 1px 6px; font-size: 8pt; }
.badge-edit { background: #fde2e1; color: #b3261e; border-radius: 4px; padding: 1px 6px; font-size: 8pt; font-weight: 600; }
.badge-no { background: #e3f4e8; color: #1a7f37; border-radius: 4px; padding: 1px 6px; font-size: 8pt; }
.cols { column-count: 3; column-gap: 16px; font-size: 8.5pt; }
.footnote { color: #7b8794; font-size: 8pt; margin-top: 24px; }
"""


def html_escape(text: object) -> str:
    s = str(text)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def stat_card(value: object, label: str) -> str:
    return f'<div class="card"><div class="value">{html_escape(value)}</div><div class="label">{html_escape(label)}</div></div>'


def badge(text: str, variant: str) -> str:
    cls = {"edit": "badge-edit", "view": "badge-view", "no": "badge-no"}.get(variant, "badge-view")
    return f'<span class="{cls}">{html_escape(text)}</span>'


def section_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html_escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
```

> Note: cells passed to `section_table` are already-rendered HTML (so callers can embed pills/badges). Callers must `html_escape` their own plain text before passing it in.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report_assets.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add report_assets.py tests/test_report_assets.py
git commit -m "feat: report CSS + HTML building blocks (cards, tables, badges)"
```

---

## Task 13: Report renderer (`report.py`)

**Files:**
- Create: `report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

`tests/test_report.py`:
```python
from datetime import datetime, timezone
from pathlib import Path
import json

from models import (
    GroupAudit, Member, AppRoleRow, SchemeGrant, ProjectRef, FilterShare,
    JqlHit, DashboardShare, ManualCheck, ExecutiveSummary,
)
from classify import derive_stats, build_summary
from report import build_html, output_basename, render


def _audit():
    a = GroupAudit("acme.atlassian.net", "jira-users", "gid-1",
                   datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc), "Igor Medeiros")
    a.members = [Member("Alice", "1", True), Member("Old", "2", False)]
    a.inactive_in_group = [Member("Old", "2", False)]
    a.app_roles = [AppRoleRow("Jira Software", "jira-software", 255, 100000, False, False)]
    a.perm_schemes = [SchemeGrant(10009, "AC Permission Scheme", ["BROWSE_PROJECTS"], None, 1)]
    a.projects_by_scheme = {10009: [ProjectRef("A0", "Application Data")]}
    a.filters_shared = [FilterShare("100", "Shared View", "Hugo", "view")]
    a.filters_jql = [JqlHit("200", "JQL Ref", "Igor", 'membersOf("jira-users")')]
    a.dashboards_shared = [DashboardShare("d1", "DQI", "John", "edit")]
    a.manual_checks = [ManualCheck("Global permissions", "no REST", "Settings > System > Global permissions")]
    a.stats = derive_stats(a)
    a.summary = build_summary(a)
    return a


def test_output_basename():
    a = _audit()
    assert output_basename(a) == "acme-jira-users-discovery-2026-05-22"


def test_build_html_contains_sections():
    html = build_html(_audit())
    for needle in ["jira-users", "Application access", "Permission schemes",
                   "Filters", "Dashboards", "membersOf(&quot;jira-users&quot;)",
                   "Manual check", "Global permissions"]:
        assert needle in html, needle


def test_render_writes_pdf_and_json(tmp_path: Path):
    pdf_path, json_path = render(_audit(), tmp_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 1000
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert data["group_name"] == "jira-users"
    assert data["stats"]["members"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'report'`.

- [ ] **Step 3: Write the implementation**

`report.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from weasyprint import HTML

from models import GroupAudit, audit_to_dict
from report_assets import CSS, html_escape, stat_card, section_table, badge


def output_basename(audit: GroupAudit) -> str:
    host = audit.instance_host.split(".")[0]
    date = audit.generated_at.strftime("%Y-%m-%d")
    return f"{host}-{audit.group_name}-discovery-{date}"


def _header(audit: GroupAudit) -> str:
    meta = (
        f"Instance: {html_escape(audit.instance_host)} &nbsp;•&nbsp; groupId "
        f"{html_escape(audit.group_id)} &nbsp;•&nbsp; Generated "
        f"{audit.generated_at.strftime('%Y-%m-%d %H:%M')} by {html_escape(audit.generated_by)} "
        f"&nbsp;•&nbsp; Source: Jira Cloud REST API v3 &nbsp;•&nbsp; Internal — confidential"
    )
    return (
        f'<div class="header"><h1>{html_escape(audit.group_name)} — Group Discovery</h1>'
        f'<div class="sub">Where the {html_escape(audit.group_name)} group is used across the '
        f'{html_escape(audit.instance_host)} tenant.</div>'
        f'<div class="meta">{meta}</div></div>'
    )


def _cards(audit: GroupAudit) -> str:
    s = audit.stats
    cards = [
        stat_card(s["members"], "TOTAL MEMBERS"),
        stat_card(s["active"], "ACTIVE"),
        stat_card(s["inactive"], "INACTIVE (STILL IN GROUP)"),
        stat_card(s["permission_schemes"], "PERMISSION SCHEMES"),
        stat_card(s["projects_affected"], "PROJECTS AFFECTED"),
        stat_card(s["filters_shared"], "FILTERS SHARED"),
        stat_card(s["dashboards_shared"], "DASHBOARDS SHARED"),
        stat_card(s["license_seats"], "LICENSE SEATS GRANTED"),
    ]
    if s.get("jql_references"):
        cards.append(stat_card(s["jql_references"], "JQL REFERENCES"))
    if s.get("custom_field_refs"):
        cards.append(stat_card(s["custom_field_refs"], "CUSTOM-FIELD REFS"))
    return f'<div class="cards">{"".join(cards)}</div>'


def _summary(audit: GroupAudit) -> str:
    sm = audit.summary
    parts = [f'<div class="callout"><b>{html_escape(sm.headline)}</b></div>']
    if sm.elevated_powers:
        items = "; ".join(html_escape(p) for p in sm.elevated_powers)
        parts.append(f'<div class="callout">Elevated powers: {items}.</div>')
    if sm.hygiene_flags:
        items = "; ".join(html_escape(f) for f in sm.hygiene_flags)
        parts.append(f'<div class="callout warn"><b>Hygiene flags:</b> {items}.</div>')
    return "<h2>Executive summary</h2>" + "".join(parts)


def _app_access(audit: GroupAudit) -> str:
    rows = [[
        html_escape(r.name), html_escape(r.key),
        f"{r.seats_used} / {r.seats_total}",
        badge("yes" if r.is_member else "no", "no" if not r.is_member else "view"),
        badge("yes" if r.is_default else "no", "no" if not r.is_default else "view"),
    ] for r in audit.app_roles]
    table = section_table(["Application role", "Key", "Seats used / total", "Member?", "Default?"], rows)
    verdict = "no" if not audit.grants_license else "YES"
    return f"<h2>1. Application access (license seats)</h2>{table}<p>Result: grants license = <b>{verdict}</b>.</p>"


def _perm_schemes(audit: GroupAudit) -> str:
    rows = []
    for sch in audit.perm_schemes:
        pills = "".join(f'<span class="pill">{html_escape(p)}</span>' for p in sch.permissions)
        tag = f' <span class="tag">{html_escape(sch.bundle_tag)}</span>' if sch.bundle_tag else ""
        rows.append([str(sch.scheme_id), html_escape(sch.scheme_name) + tag, pills, str(sch.project_count)])
    table = section_table(["#", "Scheme", "Permissions granted", "Projects"], rows)
    blocks = [table, "<h2>2b. Projects affected (by scheme)</h2>"]
    for sch in audit.perm_schemes:
        refs = audit.projects_by_scheme.get(sch.scheme_id, [])
        if not refs:
            continue
        items = "".join(f"<div><b>{html_escape(p.key)}</b> · {html_escape(p.name)}</div>" for p in refs)
        blocks.append(f"<h3>#{sch.scheme_id} — {html_escape(sch.scheme_name)} ({len(refs)} projects)</h3>"
                      f'<div class="cols">{items}</div>')
    return "<h2>2. Permission schemes</h2>" + "".join(blocks)


def _filters(audit: GroupAudit) -> str:
    shared_rows = [[html_escape(f.filter_id), html_escape(f.name), html_escape(f.owner), badge(f.access, f.access)]
                   for f in audit.filters_shared]
    jql_rows = [[html_escape(j.filter_id), html_escape(j.name), html_escape(j.owner), html_escape(j.matched_clause)]
                for j in audit.filters_jql]
    out = "<h2>3. Filters shared with the group</h2>"
    out += section_table(["Filter ID", "Name", "Owner", "Access"], shared_rows) if shared_rows else "<p>None.</p>"
    out += "<h2>3b. Filters whose JQL references the group</h2>"
    out += section_table(["Filter ID", "Name", "Owner", "Matched clause"], jql_rows) if jql_rows else "<p>None.</p>"
    return out


def _dashboards(audit: GroupAudit) -> str:
    rows = [[html_escape(d.dashboard_id), html_escape(d.name), html_escape(d.owner), badge(d.access.upper() if d.access == "edit" else d.access, d.access)]
            for d in audit.dashboards_shared]
    table = section_table(["Dashboard ID", "Name", "Owner", "Access"], rows) if rows else "<p>None.</p>"
    return f"<h2>4. Dashboards shared with the group</h2>{table}"


def _other_dimensions(audit: GroupAudit) -> str:
    rows = []
    rows.append(["Notification schemes",
                 "Not used" if not audit.notification_hits else f"{len(audit.notification_hits)} scheme(s)"])
    rows.append(["Issue security schemes",
                 "Not present" if not audit.security_hits else f"{len(audit.security_hits)} scheme(s)"])
    for r in audit.role_hits:
        note = "inert migration artifact" if not r.granted_by_any_scheme else "granted by a permission scheme"
        rows.append([f"Project role #{r.role_id} {html_escape(r.role_name)}", f"default actor — {note}"])
    for c in audit.custom_field_hits:
        rows.append([f"Custom field {html_escape(c.field_name)}", html_escape(c.detail)])
    return "<h2>5. Other dimensions checked</h2>" + section_table(["Dimension", "Result"], rows)


def _membership(audit: GroupAudit) -> str:
    out = ["<h2>6. Membership roster</h2>"]
    if audit.inactive_in_group:
        names = ", ".join(html_escape(m.display_name) for m in audit.inactive_in_group)
        out.append(f'<div class="callout warn"><b>Inactive accounts still in group:</b> {names}</div>')
    if audit.non_human:
        names = ", ".join(html_escape(m.display_name) for m in audit.non_human)
        out.append(f'<div class="callout"><b>Bot / service / test accounts:</b> {names}</div>')
    items = []
    for m in audit.members:
        flag = ' <span class="badge-edit">inactive</span>' if not m.active else ""
        items.append(f"<div>{html_escape(m.display_name)}{flag}</div>")
    out.append(f'<div class="cols">{"".join(items)}</div>')
    return "".join(out)


def _manual_checks(audit: GroupAudit) -> str:
    rows = [[html_escape(c.dimension), html_escape(c.reason), html_escape(c.ui_path)] for c in audit.manual_checks]
    note = ""
    if audit.incomplete_dimensions:
        note = (f'<div class="callout warn">Some dimensions could not be fully read this run: '
                f'{html_escape(", ".join(audit.incomplete_dimensions))}. Treat them as unverified.</div>')
    return ("<h2>7. Manual check required (no public Cloud REST read)</h2>" + note
            + section_table(["Dimension", "Why", "Where to verify"], rows))


def _footnote() -> str:
    return ('<div class="footnote">Generated read-only via Jira Cloud REST API v3 (HTTP Basic). '
            'Global permissions, automation, and workflow conditions have no public REST read endpoint '
            'and must be verified in the UI.</div>')


def build_html(audit: GroupAudit) -> str:
    body = "".join([
        _header(audit), _cards(audit), _summary(audit), _app_access(audit),
        _perm_schemes(audit), _filters(audit), _dashboards(audit),
        _other_dimensions(audit), _membership(audit), _manual_checks(audit), _footnote(),
    ])
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"


def render(audit: GroupAudit, out_dir) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = output_basename(audit)
    pdf_path = out_dir / f"{base}.pdf"
    json_path = out_dir / f"{base}.json"
    HTML(string=build_html(audit)).write_pdf(str(pdf_path))
    json_path.write_text(json.dumps(audit_to_dict(audit), indent=2))
    return pdf_path, json_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add report.py tests/test_report.py
git commit -m "feat: HTML/PDF report renderer + JSON sidecar"
```

---

## Task 14: CLI / orchestration (`auditor.py`)

**Files:**
- Create: `auditor.py`
- Test: `tests/test_auditor.py`

- [ ] **Step 1: Write the failing test**

`tests/test_auditor.py`:
```python
import pytest
from auditor import resolve_token, load_settings


def test_resolve_token_prefers_env(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "from-env")
    assert resolve_token(flag_token="from-flag", config_token="from-cfg") == "from-env"


def test_resolve_token_flag_over_config(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert resolve_token(flag_token="from-flag", config_token="from-cfg") == "from-flag"


def test_resolve_token_config_last(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert resolve_token(flag_token=None, config_token="from-cfg") == "from-cfg"


def test_resolve_token_missing_raises(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        resolve_token(flag_token=None, config_token=None)


def test_load_settings_merges_flags_over_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('base_url = "https://cfg.atlassian.net"\nemail = "cfg@x.com"\ngroups = ["a"]\nout_dir = "/tmp/cfg"\n')

    class Args:
        config = str(cfg)
        base_url = "https://flag.atlassian.net"
        email = None
        token = None
        group = ["b", "c"]
        out_dir = None

    settings = load_settings(Args())
    assert settings["base_url"] == "https://flag.atlassian.net"   # flag wins
    assert settings["email"] == "cfg@x.com"                       # falls back to config
    assert settings["groups"] == ["b", "c"]                       # flag groups win
    assert settings["out_dir"] == "/tmp/cfg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auditor.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'auditor'`.

- [ ] **Step 3: Write the implementation**

`auditor.py`:
```python
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

from jira_client import JiraClient
from sweep import collect
from report import render


def resolve_token(flag_token: str | None, config_token: str | None) -> str:
    token = os.environ.get("JIRA_API_TOKEN") or flag_token or config_token
    if not token:
        sys.exit("No API token. Set JIRA_API_TOKEN, pass --token, or put token in config.toml.")
    return token


def load_settings(args) -> dict:
    config: dict = {}
    if getattr(args, "config", None):
        with open(args.config, "rb") as fh:
            config = tomllib.load(fh)
    groups = args.group if getattr(args, "group", None) else config.get("groups", [])
    return {
        "base_url": args.base_url or config.get("base_url"),
        "email": args.email or config.get("email"),
        "config_token": config.get("token"),
        "groups": groups,
        "out_dir": args.out_dir or config.get("out_dir") or "./reports",
    }


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Audit where a Jira Cloud group is referenced.")
    p.add_argument("--config")
    p.add_argument("--base-url", dest="base_url")
    p.add_argument("--email")
    p.add_argument("--token")
    p.add_argument("--group", action="append", help="repeatable")
    p.add_argument("--out-dir", dest="out_dir")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    settings = load_settings(args)
    if not settings["base_url"] or not settings["email"]:
        sys.exit("base_url and email are required (via flags or config.toml).")
    if not settings["groups"]:
        sys.exit("No groups specified (use --group or config.toml groups=[...]).")
    token = resolve_token(getattr(args, "token", None), settings["config_token"])

    client = JiraClient(settings["base_url"], settings["email"], token)
    try:
        me = client.verify_auth()
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Auth failed against {settings['base_url']}: {exc}\n"
                 f"Note: this tool uses HTTP Basic (email + token). Bearer tokens return 403 on Cloud.")
    print(f"Authenticated as {me.get('displayName')} on {settings['base_url']}")

    out_dir = Path(settings["out_dir"])
    for group in settings["groups"]:
        print(f"Auditing group: {group} ...")
        audit = collect(client, group)
        pdf_path, json_path = render(audit, out_dir)
        flag = f"  (incomplete: {', '.join(audit.incomplete_dimensions)})" if audit.incomplete_dimensions else ""
        print(f"  -> {pdf_path}\n  -> {json_path}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auditor.py -q`
Expected: `5 passed`. Then full suite `python -m pytest -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add auditor.py tests/test_auditor.py
git commit -m "feat: CLI entrypoint — config/flag merge, token resolution, per-group loop"
```

---

## Task 15: README + finalize config example

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

`README.md`:
```markdown
# Jira Group Auditor

Read-only tool that sweeps a Jira **Cloud** site for every place a group is referenced and
produces a per-group PDF report + JSON sidecar.

## What it checks (via REST)
Membership, application/license roles, permission schemes (+ affected projects), notification
schemes, issue-security schemes, project roles, filters (shares **and** JQL bodies), dashboards,
agile boards' backing-filter JQL, and group-picker custom-field defaults.

## What it can't check (reported as "manual check required")
Global permissions, automation rules, workflow conditions/validators, and raw dashboard-gadget
JQL — none have a public Cloud REST read endpoint. The report lists exactly where to verify each
in the UI.

## Install
```bash
pip install -r requirements.txt
```

## Usage
```bash
export JIRA_API_TOKEN=ATATT...          # preferred (keeps the token out of files & history)
python auditor.py --config config.toml
# or all by flags:
python auditor.py --base-url https://acme.atlassian.net --email you@acme.com \
                  --group jira-users --group jira-users-cloud --out-dir ./reports
```

Auth is HTTP Basic (`email` + API token). **Bearer tokens return 403 on Cloud** — use a token
from id.atlassian.com.

## Output
Per group: `<instance>-<group>-discovery-<YYYY-MM-DD>.pdf` and `.json` in `--out-dir`.

## Tests
```bash
python -m pytest -q
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with usage, coverage, and the Basic-not-Bearer note"
```

---

## Task 16: Live acceptance run (oracle)

This task needs **live credentials for a real tenant** and confirms the tool reproduces the
known ground truth from a prior manual group-discovery report.

- [ ] **Step 1: Run against the real tenant**

```bash
cd jira-group-auditor
export JIRA_API_TOKEN='<your API token>'
python auditor.py --base-url https://acme.atlassian.net \
                  --email you@example.com \
                  --group example-group --out-dir ./reports
```

- [ ] **Step 2: Verify against the oracle**

Open `./reports/<instance>-<group>-discovery-<today>.json` and confirm each stat matches your
known ground truth:
```
stats.members            == <expected member count>
stats.active             == <expected active count>
stats.inactive           == <expected inactive count>
stats.permission_schemes == <expected scheme count>
stats.projects_affected  == <expected project count>
stats.filters_shared     == <expected filter count>
stats.dashboards_shared  == <expected dashboard count>
stats.license_seats      == <expected seat count>
```
Expected: all match. If any differs, investigate the relevant collector before declaring done
(do **not** adjust the oracle to match the code).

- [ ] **Step 3: Spot-check the PDF**

Open the generated PDF and confirm the header, 8 stat cards, exec summary, permission-scheme
pills + bundle tags, projects-by-scheme columns, filters/dashboards tables, membership roster
with inactive badges, the manual-check section, and the per-page footer all render.

---

## Self-review notes (filled during planning)

- **Spec coverage:** config/invocation (T1, T15, T14) · models (T2) · 11 REST dimensions
  (T7 membership+app, T8 perm schemes+projects, T9 notif/security/roles, T10 filters/dashboards/boards,
  T11 custom fields) · JQL parser (T3) · matchers (T4) · classify/stats/summary (T5) · client
  pagination/backoff/auth (T6) · manual-check section (T11) · report PDF+JSON (T12, T13) ·
  error isolation (T11 `_guard`, surfaced in report T13 `_manual_checks`) · live oracle (T16).
- **Type consistency:** `holder_matches_group(holder, group_name, group_id)` used identically in
  T8/T9/T10. `find_group_references(jql, group_name, group_id)` used in T10. `GroupAudit` field
  names match between T2 (definition), T11 (population), and T13 (rendering). `derive_stats` keys
  (`members/active/inactive/permission_schemes/projects_affected/filters_shared/dashboards_shared/license_seats/jql_references/custom_field_refs`)
  match between T5 (definition) and T13 (`_cards`). `render()`/`output_basename()`/`build_html()`
  signatures match between T13 and T16/T14.
- **No placeholders:** every code step contains complete, runnable code.
```
