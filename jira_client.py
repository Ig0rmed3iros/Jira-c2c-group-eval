from __future__ import annotations

import time

import requests


class JiraClient:
    def __init__(self, base_url: str, email: str, token: str, session=None, max_retries: int = 5):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.auth = (email, token)
        self.session.headers.update({"Accept": "application/json"})
        self.max_retries = max_retries

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.base_url}{path}"

    def get(self, path: str, params: dict | None = None) -> dict:
        last = None
        for attempt in range(self.max_retries):
            resp = self.session.get(self._url(path), params=params)
            last = resp
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        last.raise_for_status()
        raise RuntimeError("unreachable")

    def verify_auth(self) -> dict:
        return self.get("/rest/api/3/myself")

    def paginate(self, path: str, params: dict | None = None, values_key: str = "values") -> list:
        params = dict(params or {})
        page = 100
        params["maxResults"] = page
        start = 0
        out: list = []
        while True:
            params["startAt"] = start
            data = self.get(path, params)
            vals = data.get(values_key, [])
            out.extend(vals)
            if data.get("isLast") is True:
                break
            if len(vals) < page:
                break
            start += page
        return out
