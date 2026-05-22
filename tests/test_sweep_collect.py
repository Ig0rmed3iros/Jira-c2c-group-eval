from datetime import datetime, timezone
import sweep
from models import GroupAudit, Member


def test_collect_custom_fields_group_picker():
    class Stub:
        def get(self, path, params=None):
            if path == "/rest/api/3/field":
                return [{"id": "customfield_1", "name": "Approver Group",
                         "schema": {"custom": "com.atlassian.jira.plugin.system.customfieldtypes:grouppicker"}}]
            raise KeyError(path)

        def paginate(self, path, params=None, values_key="values"):
            if path == "/rest/api/3/field/customfield_1/context":
                return [{"id": "ctx-1", "name": "Default Context"}]
            if path == "/rest/api/3/field/customfield_1/context/defaultValue":
                return [{"contextId": "ctx-1", "type": "group", "groupId": "gid-1"}]
            return []

    hits = sweep.collect_custom_fields(Stub(), "jira-users", "gid-1")
    assert len(hits) == 1 and hits[0].field_id == "customfield_1"


def test_default_manual_checks_listed():
    checks = sweep.default_manual_checks()
    dims = {c.dimension for c in checks}
    assert "Global permissions" in dims
    assert "Automation rules" in dims


def test_collect_isolates_failing_dimension(monkeypatch):
    # resolve_group + verify succeed; one collector raises -> recorded, run continues
    monkeypatch.setattr(sweep, "resolve_group", lambda c, n: ("gid-1", [Member("Alice", "1", True)]))
    monkeypatch.setattr(sweep, "collect_app_access", lambda c, n, g: ([], False))
    monkeypatch.setattr(sweep, "fetch_permission_schemes", lambda c: {"permissionSchemes": []})
    monkeypatch.setattr(sweep, "collect_permission_schemes", lambda *a: ([], {}))
    monkeypatch.setattr(sweep, "granted_role_ids_from_schemes", lambda p: set())
    monkeypatch.setattr(sweep, "collect_project_roles", lambda *a, **k: [])
    monkeypatch.setattr(sweep, "collect_notification_schemes", lambda *a: [])
    monkeypatch.setattr(sweep, "collect_security_schemes", lambda *a: [])
    def boom(*a, **k):
        raise RuntimeError("403")
    monkeypatch.setattr(sweep, "collect_filters", boom)            # this one fails
    monkeypatch.setattr(sweep, "collect_dashboards", lambda *a: [])
    monkeypatch.setattr(sweep, "collect_boards", lambda *a, **k: [])
    monkeypatch.setattr(sweep, "collect_custom_fields", lambda *a: [])

    class Stub:
        base_url = "https://acme.atlassian.net"
        def verify_auth(self):
            return {"displayName": "Igor"}

    audit = sweep.collect(Stub(), "jira-users")
    assert isinstance(audit, GroupAudit)
    assert audit.group_id == "gid-1"
    assert "filters" in audit.incomplete_dimensions
    assert audit.summary is not None and audit.stats["members"] == 1
