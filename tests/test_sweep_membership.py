from sweep import resolve_group, collect_app_access
from models import Member


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}

    def get(self, path, params=None):
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map[path]


def test_resolve_group_returns_id_and_members():
    client = StubClient(
        get_map={"/rest/api/3/group/bulk": {"values": [{"name": "jira-users", "groupId": "gid-1"}]}},
        paginate_map={"/rest/api/3/group/member": [
            {"accountId": "1", "displayName": "Alice", "active": True, "accountType": "atlassian", "emailAddress": "a@x.com"},
            {"accountId": "2", "displayName": "Old", "active": False, "accountType": "atlassian"},
        ]},
    )
    gid, members = resolve_group(client, "jira-users")
    assert gid == "gid-1"
    assert members[0] == Member("Alice", "1", True, "atlassian", "a@x.com")
    assert members[1].active is False


def test_collect_app_access_no_membership_means_no_license():
    client = StubClient(get_map={"/rest/api/3/applicationrole": [
        {"key": "jira-software", "name": "Jira Software", "groups": ["jira-software-users"],
         "defaultGroups": [], "userCount": 255, "numberOfSeats": 100000,
         "groupDetails": [{"name": "jira-software-users", "groupId": "gid-x"}],
         "defaultGroupsDetails": []},
    ]})
    rows, grants = collect_app_access(client, "jira-users", "gid-1")
    assert grants is False
    assert rows[0].seats_used == 255 and rows[0].seats_total == 100000
    assert rows[0].is_member is False


def test_collect_app_access_membership_grants_license():
    client = StubClient(get_map={"/rest/api/3/applicationrole": [
        {"key": "jira-software", "name": "Jira Software", "groups": ["jira-users"],
         "defaultGroups": [], "userCount": 10, "numberOfSeats": 100,
         "groupDetails": [{"name": "jira-users", "groupId": "gid-1"}], "defaultGroupsDetails": []},
    ]})
    rows, grants = collect_app_access(client, "jira-users", "gid-1")
    assert grants is True
    assert rows[0].is_member is True
