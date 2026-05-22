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
