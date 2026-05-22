from __future__ import annotations

from models import AppRoleRow, Member, ProjectRef, SchemeGrant
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
