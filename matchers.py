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
