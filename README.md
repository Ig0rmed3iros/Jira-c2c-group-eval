# Jira Group Auditor

Read-only tool that sweeps a Jira **Cloud** site for every place a group is referenced and
produces a per-group PDF report + JSON sidecar.

## What it checks (via REST)
Membership, application/license roles, permission schemes (+ affected projects), notification
schemes, issue-security schemes, project roles, filters (shares **and** JQL bodies), dashboards,
agile boards' backing-filter JQL, and group-picker custom-field defaults.

## What it can't check (reported as "manual check required")
Global permissions, automation rules, workflow conditions/validators, and raw dashboard-gadget
JQL — none have a public Cloud REST read endpoint. The report lists exactly where to verify each
in the UI.

## Install
```bash
pip install -r requirements.txt
```

## Usage
```bash
export JIRA_API_TOKEN=ATATT...          # preferred (keeps the token out of files & history)
python3 auditor.py --config config.toml
# or all by flags:
python3 auditor.py --base-url https://acme.atlassian.net --email you@acme.com \
                   --group jira-users --group jira-users-cloud --out-dir ./reports
```

Auth is HTTP Basic (`email` + API token). **Bearer tokens return 403 on Cloud** — use a token
from id.atlassian.com.

## Output
Per group: `<instance>-<group>-discovery-<YYYY-MM-DD>.pdf` and `.json` in `--out-dir`.

## Tests
```bash
python3 -m pytest -q
```
