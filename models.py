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
