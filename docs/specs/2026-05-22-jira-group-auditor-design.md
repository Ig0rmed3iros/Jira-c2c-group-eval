# Jira Group Auditor — Design Spec

- **Date:** 2026-05-22
- **Status:** Implemented & published 2026-05-22
- **Author:** Igor Medeiros (with Claude)
- **Location:** published (public) at https://github.com/Ig0rmed3iros/Jira-c2c-group-eval

## 1. Goal

Generalize the one-off `example-group-discovery` audit into a reusable, configurable
Python tool. The user supplies a base URL, credentials, and one or more group names; the tool
sweeps the entire Jira Cloud site for every place that group is referenced and emits, **per
group**, a high-quality PDF report (matching the existing `example-group-discovery-2026-05-21.pdf`
visual) plus a machine-readable JSON sidecar.

The defining requirement: **sweep everything the REST API exposes** — permissions, license
roles, filters (including JQL bodies), dashboards, boards, notification/security schemes,
project roles, and group-picker custom fields — and **honestly flag** the dimensions Jira
Cloud does not expose over public REST (global permissions, automation, workflow conditions)
as a clearly-labeled "manual check required" section.

## 2. Non-goals

- **No Server / Data Center support.** Cloud only (HTTP Basic `email:token`). Bearer auth is
  explicitly out (it returns 403 on the target tenant).
- **No write operations.** Strictly read-only. The tool never mutates the tenant.
- **No browser automation.** Dimensions without a public REST read endpoint are reported as
  manual-check items, not scraped from the admin UI.
- **No CI.** No continuous-integration pipeline. (Originally scoped as a local-only project; it
  was later published to a public GitHub repo — see Location above.)

## 3. Configuration & invocation

Two interchangeable ways to configure:

```
python auditor.py --config config.toml
python auditor.py --base-url https://acme.atlassian.net \
                  --email you@example.com \
                  --group jira-users --group jira-users-cloud
```

- **Token resolution order:** `JIRA_API_TOKEN` env var → `--token` flag → `config.toml`.
  Env var is preferred so the secret stays out of shell history and config files.
- `--out-dir` defaults to `./reports`.
- `config.example.toml` ships as a template; real `config.toml` is gitignored.
- Multiple `--group` flags (or a `[groups]` list in TOML) are allowed; each group is audited
  independently and produces its own output pair.

### Output naming
Per group: `<instance-host>-<group-slug>-discovery-<YYYY-MM-DD>.pdf` and `.json`
(e.g. `acme-example-group-discovery-2026-05-22.pdf`).

## 4. Architecture

Small module set in one folder. Boundaries chosen so the two highest-risk units (the JQL
parser and the group matchers) are independently unit-testable.

```
jira-group-auditor/
  auditor.py            # CLI entry: config/flags, auth verify, per-group orchestration loop
  jira_client.py        # Basic-auth session, paginated GET, 429 backoff, typed fetchers
  sweep.py              # 11 collectors + group-ref matching + JQL parser -> GroupAudit
  report.py             # GroupAudit -> HTML -> WeasyPrint PDF + JSON sidecar
  report_assets.py      # CSS + HTML scaffold (kept apart so report.py stays logic)
  config.example.toml
  requirements.txt      # requests, weasyprint  (no Jinja2 — string templating)
  README.md
  tests/
    test_jql_parser.py
    test_matchers.py
    test_classify.py
    test_report.py
    fixtures/*.json
```

Dependencies are deliberately minimal: `requests` + `weasyprint` only (both already installed
locally; WeasyPrint 68.1, requests 2.31).

### Data flow
`config → jira_client (auth verified via /myself) → sweep.collect(group) → GroupAudit dataclass
→ report.render(GroupAudit) → writes PDF + JSON`. Loop per group; groups are independent.

## 5. Data model

`sweep.collect(group_name) -> GroupAudit`, a dataclass capturing everything the report needs:

```
GroupAudit:
  instance_host: str
  group_name: str
  group_id: str
  generated_at: datetime
  generated_by: str                 # displayName from /myself

  # membership
  members: list[Member]             # display_name, account_id, active, account_type, email?
  member_total / active / inactive: int
  inactive_in_group: list[Member]
  non_human: list[Member]           # bot/service/test heuristic matches

  # license
  app_roles: list[AppRoleRow]       # name, key, seats_used, seats_total, is_member, is_default
  grants_license: bool

  # permissions
  perm_schemes: list[SchemeGrant]   # id, name, permissions[], bundle_tag, project_count
  projects_by_scheme: dict[int, list[ProjectRef]]   # scheme_id -> [key·name]

  # other dimensions
  notification_hits: list[...]
  security_hits: list[...]
  role_hits: list[RoleHit]          # role id/name, is_default_actor, granted_by_any_scheme

  # sharing & jql
  filters_shared: list[FilterShare]     # id, name, owner, access(view|edit)
  filters_jql: list[JqlHit]             # id, name, owner, matched_clause
  dashboards_shared: list[DashboardShare]  # id, name, owner, access(view|edit)
  custom_field_hits: list[CustomFieldHit]  # field id/name, context, default refs group

  # coverage & gaps
  manual_checks: list[ManualCheck]      # dimension, reason, ui_path
  incomplete_dimensions: list[str]      # dimensions that errored mid-run

  # derived
  stats: dict[str, int|str]             # the at-a-glance card values
  summary: ExecutiveSummary             # rule-derived verdict + flags
```

The JSON sidecar is this dataclass serialized.

## 6. Sweep dimensions

### Covered via Cloud REST v3 / Agile
1. **Group + membership** — resolve name→groupId (`GET /rest/api/3/group/bulk?groupName=`);
   members via `GET /rest/api/3/group/member?groupId=&includeInactiveUsers=true` (paginated).
   Flag inactive accounts; flag likely bot/service/test accounts (accountType=`app` plus a
   name heuristic list: api, bot, svc, service, splunk, airflow, pentester, guest,
   administrator, test, etc.).
2. **Application access / license seats** — `GET /rest/api/3/applicationrole`. For each app
   role, is the group a member or a default group? Surface seats used/total. Verdict:
   `grants_license = any(is_member or is_default)`.
3. **Permission schemes** — `GET /rest/api/3/permissionscheme?expand=permissions,group`. Collect
   permission grants whose holder is the group (match by groupId and by name). Classify the
   set of permissions per scheme into a `bundle_tag` (e.g. "standard collaborator",
   "broad assignee pool" when ASSIGNABLE_USER present, "worklog" when Work On / Transition).
   Map each scheme to affected projects via `GET /rest/api/3/project/search` (paginated) +
   each project's permission scheme association.
4. **Notification schemes** — `GET /rest/api/3/notificationscheme?expand=all`; events whose
   notification holder is the group.
5. **Issue security schemes** — `GET /rest/api/3/issuesecurityschemes` (+ levels' members);
   group as a security-level member.
6. **Project roles** — `GET /rest/api/3/role`; group as a default actor. Cross-check whether
   any permission scheme grants to that role → detect inert migration artifacts (default actor
   but no scheme references the role).
7. **Filters** — `GET /rest/api/3/filter/search?expand=jql,sharePermissions,editPermissions,owner`
   (paginated, admin scope). Two finding types:
   (a) **shared/editable to the group** (sharePermissions/editPermissions of type `group`);
   (b) **JQL body references the group** (feeds the JQL parser, below).
8. **Dashboards** — `GET /rest/api/3/dashboard/search?expand=sharePermissions,editPermissions`
   (paginated). Shared / edit-to-group; EDIT access flagged distinctly.
9. **Boards (Agile)** — `GET /rest/agile/1.0/board`; resolve each board's backing filter and
   feed its JQL into the parser. A board surfaces if its filter references or is shared to the
   group.

### JQL reference parsing (applied to all collected JQL)
Scan every JQL string (filter bodies + board filter bodies) for references to the group:
- `membersOf("<group>")` / `membersOf(<groupId>)` / `membersOf(<group>)` (quoted or bare)
- `group = "<group>"`, `group in ("<group>", ...)`
- quoted group-name needles in user-typed fields (assignee/reporter/watcher `in membersOf(...)`)

Matching needles = the group **display name** and the **groupId**. Each hit records the
filter/board id+name+owner and the **exact matching clause** (substring), so a reviewer can
see why it matched. Guard against the false-positive trap where a project key or arbitrary
text merely contains the group name — only count structured references (membersOf/group
operators) and quoted exact-name matches, not bare substrings.

### Custom fields
`GET /rest/api/3/field`; identify custom fields of type group-picker / multi-group-picker.
For each, check its context default value(s) (`GET /rest/api/3/field/{id}/context/defaultValue`)
for a reference to the group.

### Reported as "manual check required" (no public Cloud REST read)
Each item names the dimension, the reason, and the exact UI path to verify:
- **Global permissions** (Browse users & groups, Bulk change, Share objects, etc.) →
  *Settings → System → Global permissions*.
- **Automation rules** (group conditions/actions) → *Project / Global automation*.
- **Workflow conditions/validators** referencing the group → *workflow editor* (best-effort;
  the workflow REST surface is too gnarly to rely on).
- **Dashboard gadget raw JQL** → individual gadget config.

## 7. Error handling

- **Auth verified first** via `GET /rest/api/3/myself`. On 401/403, print a clear message
  including the Basic-not-Bearer reminder and which credential field is suspect.
- **Per-dimension isolation:** each collector is wrapped so a 403/500/timeout on one endpoint
  records that dimension in `incomplete_dimensions` (and a manual-check note) instead of
  aborting the whole run. The report visibly marks any incomplete dimension — a partial run is
  never silently presented as complete.
- **Pagination helper** with exponential backoff on HTTP 429.
- **Unknown group name** → error that lists close matches from `GET /rest/api/3/groups/picker`.

## 8. Report / output

Reproduces the existing report 1:1, generalized:
- Gradient header banner + metadata strip (instance · groupId · generated date/by · source ·
  confidential tag).
- **8 stat cards**, data-derived: total members / active / inactive / permission schemes /
  projects affected / filters shared / dashboards shared / license seats — with JQL-reference
  and custom-field counts surfaced where non-zero.
- **Executive summary** (rule-derived): license verdict; elevated powers beyond the standard
  browse-comment bundle (ASSIGNABLE_USER, Transition/Work On Issues, admin perms); hygiene
  flags (inactive-in-group, bots present, EDIT-shared dashboards, over-broad assignable pools).
- Section tables: application access; permission schemes (permission pills + bundle tags);
  projects-by-scheme (multi-column key·name lists); filters shared; filters with JQL refs;
  dashboards shared; other dimensions checked; membership roster (inactive/bot badges).
- Per-page footer with page counter; closing footnote on REST/Basic source + the
  global-permissions gap.
- **JSON sidecar** = serialized `GroupAudit`, for diffing future runs.

Styling is produced as HTML+CSS rendered to PDF by WeasyPrint (string-templated in
`report_assets.py`; no Jinja2).

### Known tradeoff
The original exec summary had hand-written nuance. The generic tool produces a **rule-derived**
summary — accurate and well-structured, slightly more templated in voice. (Future option, not
in scope now: a `--notes` flag to inject hand-written summary lines.)

## 9. Testing strategy

- **Unit (synthetic fixtures, no live calls):**
  - JQL parser: membersOf variants, `group=`/`in()`, quoted/unquoted, groupId match, and the
    false-positive trap (project key resembling the group name).
  - Matchers: holder match by name *and* groupId across scheme/notification/security holders.
  - Classifier: permission-set → bundle_tag; bot/inactive heuristics; stat + summary derivation.
- **Render smoke:** `report.render(sample_audit)` emits HTML containing all expected sections
  and writes a valid (non-empty, openable) PDF.
- **Live acceptance (oracle):** run against a group whose footprint you already know from a
  prior manual audit, and assert the tool reproduces that ground truth — member counts
  (total/active/inactive), permission-scheme and affected-project counts, filter/dashboard
  share counts, and the license-seat verdict. Comparing against a known-good prior result is
  the strongest correctness gate available.

## 10. Decisions log

- **B (module folder)** chosen over single-file / two-file for testability of the JQL parser
  and matchers. (Approved 2026-05-22.)
- **Cloud-only, Basic auth.** (Approved.)
- **Manual-check section** for global permissions etc. rather than browser automation. (Approved.)
- **One PDF + one JSON sidecar per group** (not a combined report). (Approved.)
- **Auto-generated exec summary** accepted; `--notes` injection deferred. (Approved.)
