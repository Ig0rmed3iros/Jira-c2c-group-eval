from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from models import (
    AppRoleRow, Member, ProjectRef, SchemeGrant, RoleHit, SchemeMemberHit,
    FilterShare, JqlHit, DashboardShare, CustomFieldHit, ManualCheck, GroupAudit,
)
from jql import find_group_references
from matchers import holder_matches_group
from classify import classify_bundle, is_non_human, derive_stats, build_summary


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
        params={"expand": "owner,sharePermissions,editPermissions"},
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
