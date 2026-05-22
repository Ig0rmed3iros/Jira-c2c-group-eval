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
