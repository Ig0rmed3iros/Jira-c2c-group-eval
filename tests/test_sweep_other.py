from sweep import collect_notification_schemes, collect_security_schemes, collect_project_roles


class StubClient:
    def __init__(self, get_map=None, paginate_map=None):
        self.get_map = get_map or {}
        self.paginate_map = paginate_map or {}

    def get(self, path, params=None):
        return self.get_map[path]

    def paginate(self, path, params=None, values_key="values"):
        return self.paginate_map.get(path, [])


def test_notification_hit():
    client = StubClient(paginate_map={"/rest/api/3/notificationscheme": [
        {"id": 1, "name": "Default", "notificationSchemeEvents": [
            {"event": {"name": "Issue Created"},
             "notifications": [{"notificationType": "Group", "type": "group", "parameter": "jira-users"}]},
        ]},
    ]})
    hits = collect_notification_schemes(client, "jira-users", "gid-1")
    assert len(hits) == 1 and hits[0].scheme_id == 1


def test_security_no_hit():
    client = StubClient(
        get_map={"/rest/api/3/issuesecurityschemes": {"issueSecuritySchemes": [{"id": 7, "name": "Sec"}]}},
        paginate_map={"/rest/api/3/issuesecurityschemes/level/member": [
            {"holder": {"type": "group", "parameter": "other"}},
        ]},
    )
    hits = collect_security_schemes(client, "jira-users", "gid-1")
    assert hits == []


def test_project_role_inert_artifact():
    client = StubClient(get_map={"/rest/api/3/role": [
        {"id": 10037, "name": "JIRA Users (migrated 2)",
         "actors": [{"type": "atlassian-group-role-actor", "name": "jira-users",
                     "actorGroup": {"name": "jira-users", "groupId": "gid-1"}}]},
    ]})
    # no scheme grants to role 10037 -> inert
    hits = collect_project_roles(client, "jira-users", "gid-1", granted_role_ids=set())
    assert len(hits) == 1
    assert hits[0].is_default_actor is True
    assert hits[0].granted_by_any_scheme is False
