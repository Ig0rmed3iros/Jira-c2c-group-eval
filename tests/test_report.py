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
