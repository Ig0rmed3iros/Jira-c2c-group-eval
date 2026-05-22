from sweep import collect_filters, collect_dashboards, collect_boards


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}

    def get(self, path, params=None):
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map.get(path, [])


def test_collect_filters_share_and_jql():
    client = StubClient(paginate_map={"/rest/api/3/filter/search": [
        {"id": "100", "name": "Shared View", "owner": {"displayName": "Hugo"},
         "jql": "project = AC", "sharePermissions": [{"type": "group", "group": {"name": "jira-users", "groupId": "gid-1"}}],
         "editPermissions": []},
        {"id": "200", "name": "JQL Ref", "owner": {"displayName": "Igor"},
         "jql": 'assignee in membersOf("jira-users")', "sharePermissions": [], "editPermissions": []},
        {"id": "300", "name": "Unrelated", "owner": {"displayName": "Bob"},
         "jql": "project = X", "sharePermissions": [], "editPermissions": []},
    ]})
    shared, jql_hits = collect_filters(client, "jira-users", "gid-1")
    assert [s.filter_id for s in shared] == ["100"]
    assert shared[0].access == "view"
    assert [j.filter_id for j in jql_hits] == ["200"]
    assert jql_hits[0].matched_clause == 'membersOf("jira-users")'


def test_collect_dashboards_edit_flag():
    client = StubClient(paginate_map={"/rest/api/3/dashboard/search": [
        {"id": "d1", "name": "DQI", "owner": {"displayName": "John"},
         "sharePermissions": [], "editPermissions": [{"type": "group", "group": {"name": "jira-users", "groupId": "gid-1"}}]},
    ]})
    shared = collect_dashboards(client, "jira-users", "gid-1")
    assert shared[0].access == "edit"
    assert shared[0].owner == "John"


def test_collect_boards_backing_filter_jql():
    client = StubClient(
        paginate_map={"/rest/agile/1.0/board": [{"id": 5, "name": "ACL Board"}]},
        get_map={
            "/rest/agile/1.0/board/5/configuration": {"filter": {"id": "900"}},
            "/rest/api/3/filter/900": {"id": "900", "name": "ACL Board", "owner": {"displayName": "Richard"},
                                       "jql": 'group = "jira-users"'},
        },
    )
    jql_hits = collect_boards(client, "jira-users", "gid-1", already_seen_filter_ids={"200"})
    assert jql_hits[0].filter_id == "900"
    assert jql_hits[0].matched_clause == 'group = "jira-users"'
