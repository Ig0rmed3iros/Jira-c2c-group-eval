from __future__ import annotations

from models import AppRoleRow, Member, ProjectRef, SchemeGrant, RoleHit, SchemeMemberHit
from matchers import holder_matches_group
from classify import classify_bundle


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
