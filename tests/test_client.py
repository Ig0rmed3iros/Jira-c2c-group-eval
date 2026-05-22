import pytest
from jira_client import JiraClient


class FakeResp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.auth = None
        self.headers = {}

    def get(self, url, params=None):
        # snapshot params — paginate mutates one dict in place across pages
        self.calls.append((url, dict(params) if params else params))
        return self._responses.pop(0)


def _client(session):
    return JiraClient("https://x.atlassian.net", "e@x.com", "tok", session=session)


def test_get_returns_json():
    c = _client(FakeSession([FakeResp(200, {"ok": True})]))
    assert c.get("/rest/api/3/myself") == {"ok": True}


def test_get_retries_on_429(monkeypatch):
    monkeypatch.setattr("jira_client.time.sleep", lambda *_: None)
    session = FakeSession([FakeResp(429, headers={"Retry-After": "0"}), FakeResp(200, {"ok": 1})])
    c = _client(session)
    assert c.get("/x") == {"ok": 1}
    assert len(session.calls) == 2


def test_paginate_offset_two_pages():
    page1 = FakeResp(200, {"values": [{"id": 1}] * 100, "isLast": False})
    page2 = FakeResp(200, {"values": [{"id": 2}], "isLast": True})
    c = _client(FakeSession([page1, page2]))
    out = c.paginate("/rest/api/3/filter/search")
    assert len(out) == 101


def test_paginate_custom_values_key():
    page = FakeResp(200, {"dashboards": [{"id": "d1"}], "isLast": True})
    c = _client(FakeSession([page]))
    out = c.paginate("/rest/api/3/dashboard/search", values_key="dashboards")
    assert out == [{"id": "d1"}]


def test_paginate_respects_server_maxresults_cap():
    # server caps page at 50 despite the request, omits isLast, uses total to terminate.
    # paginate must advance startAt by the RETURNED count (50), not the requested page (100).
    p1 = FakeResp(200, {"values": [{"i": i} for i in range(50)], "total": 120, "maxResults": 50})
    p2 = FakeResp(200, {"values": [{"i": i} for i in range(50)], "total": 120, "maxResults": 50})
    p3 = FakeResp(200, {"values": [{"i": i} for i in range(20)], "total": 120, "maxResults": 50})
    session = FakeSession([p1, p2, p3])
    c = _client(session)
    out = c.paginate("/rest/api/3/group/member")
    assert len(out) == 120
    assert session.calls[0][1]["startAt"] == 0
    assert session.calls[1][1]["startAt"] == 50
    assert session.calls[2][1]["startAt"] == 100
