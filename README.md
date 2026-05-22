# Jira Group Auditor

A read-only command-line tool that sweeps a **Jira Cloud** site for every place a group is
referenced and produces, **per group**, a polished PDF report plus a machine-readable JSON
sidecar. Useful for access reviews, group cleanup, and Cloud-to-Cloud migration planning.

It is **strictly read-only** — it only issues `GET` requests and never modifies the tenant.

## What it checks (via the public Cloud REST API)
- Group **membership** — flags inactive accounts and likely bot/service/test accounts
- **Application / license roles** — whether the group grants a paid seat
- **Permission schemes** + the projects each affects, with a behaviour-bundle tag
- **Notification schemes**, **issue-security schemes**, **project roles** (incl. inert migration artifacts)
- **Filters** — both share permissions *and* JQL bodies that reference the group (`membersOf(...)`, `group = ...`)
- **Dashboards** — view/edit shares (EDIT flagged)
- **Agile boards** — backing-filter JQL
- **Group-picker custom fields** — context default values

## What it can't check (flagged as "manual check required")
Global permissions, automation rules, workflow conditions/validators, and raw dashboard-gadget
JQL have no public Cloud REST read endpoint. The report lists each one with the exact UI path to
verify it manually.

## Requirements
- Python 3.11+
- `requests`, `weasyprint` (see `requirements.txt`). WeasyPrint renders the PDF; on some systems
  it needs native libraries (pango/cairo) — see the WeasyPrint install docs.

## Install
```bash
pip install -r requirements.txt
```

## Usage
```bash
# token via env var is preferred (keeps it out of files & shell history)
export JIRA_API_TOKEN=ATATT...

# with a config file:
python3 auditor.py --config config.toml

# or entirely via flags (repeat --group for multiple groups):
python3 auditor.py \
  --base-url https://acme.atlassian.net \
  --email you@example.com \
  --group jira-users --group jira-users-cloud \
  --out-dir ./reports
```

**Auth:** HTTP Basic (`email` + API token from id.atlassian.com). **Bearer tokens return 403 on
Cloud** — use Basic. Token resolution order: `JIRA_API_TOKEN` env var → `--token` flag → `config.toml`.

Copy `config.example.toml` → `config.toml` (gitignored) to drive it from a config file.

## Output
For each group, written to `--out-dir` (default `./reports`):
- `<instance>-<group>-discovery-<YYYY-MM-DD>.pdf` — a sectioned report: at-a-glance stat cards,
  an auto-generated executive summary (license verdict, elevated powers, hygiene flags),
  application access, permission schemes + affected projects, filters (shares + JQL refs),
  dashboards, other dimensions, the membership roster, and the manual-check section.
- `<instance>-<group>-discovery-<YYYY-MM-DD>.json` — the same findings as structured data, for
  diffing across runs.

## Project layout
```
auditor.py        # CLI entry: config/flags, auth, per-group loop
jira_client.py    # Basic-auth REST client (pagination, 429 backoff)
sweep.py          # the collectors + orchestration -> GroupAudit
jql.py            # JQL group-reference parser
matchers.py       # group holder matching (by name + groupId)
classify.py       # permission-bundle tags, bot heuristic, stats, summary
report.py         # GroupAudit -> HTML -> PDF + JSON
report_assets.py  # report CSS + HTML building blocks
tests/            # pytest suite (58 tests; no live calls)
docs/             # design spec + implementation plan
```

## Notes / Cloud API caveats baked in
- Several paginated endpoints **cap `maxResults` below the requested value** (e.g. `/group/member`
  caps at 50). The client advances by the *returned* count and terminates via `isLast`/`total`.
- `/dashboard/search` returns rows under `values` (not `dashboards`) and omits the owner unless
  `expand=owner` is requested.
- urllib3 + brotli can fail to decode large responses, so the client requests
  `Accept-Encoding: gzip, deflate`.

## Resilience
Each dimension is swept independently — if one endpoint errors (e.g. a permission gap), that
dimension is recorded as incomplete and the run continues, so a partial report is never silently
presented as complete.

## Tests
```bash
python3 -m pytest -q
```

## License
MIT — see [LICENSE](LICENSE).
