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
