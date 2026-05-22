from sweep import collect_permission_schemes


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map[path]


SCHEMES = {
    "permissionSchemes": [
        {"id": 10009, "name": "AC Permission Scheme", "permissions": [
            {"permission": "BROWSE_PROJECTS", "holder": {"type": "group", "parameter": "jira-users"}},
            {"permission": "ADD_COMMENTS", "holder": {"type": "group", "parameter": "jira-users"}},
        ]},
        {"id": 10006, "name": "MS Scheme", "permissions": [
            {"permission": "ASSIGNABLE_USER", "holder": {"type": "group", "value": "gid-1"}},
        ]},
        {"id": 99999, "name": "Unrelated", "permissions": [
            {"permission": "BROWSE_PROJECTS", "holder": {"type": "group", "parameter": "other"}},
        ]},
    ]
}


def _client():
    return StubClient(
        get_map={
            "/rest/api/3/project/AC1/permissionscheme": {"id": 10009},
            "/rest/api/3/project/MS1/permissionscheme": {"id": 10006},
        },
        paginate_map={"/rest/api/3/project/search": [
            {"key": "AC1", "name": "AC One"},
            {"key": "MS1", "name": "Managed Services"},
        ]},
    )


def test_collect_permission_schemes_matches_and_counts():
    client = _client()
    schemes, projects_by_scheme = collect_permission_schemes(client, "jira-users", "gid-1", SCHEMES)
    ids = {s.scheme_id for s in schemes}
    assert ids == {10009, 10006}            # unrelated scheme excluded
    by_id = {s.scheme_id: s for s in schemes}
    assert set(by_id[10009].permissions) == {"BROWSE_PROJECTS", "ADD_COMMENTS"}
    assert by_id[10009].bundle_tag is None
    assert by_id[10006].bundle_tag == "broad assignee pool"
    assert by_id[10009].project_count == 1
    assert projects_by_scheme[10009][0].key == "AC1"
