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
