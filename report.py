from __future__ import annotations

import json
from pathlib import Path

from weasyprint import HTML

from models import GroupAudit, audit_to_dict
from report_assets import CSS, html_escape, stat_card, section_table, badge


def output_basename(audit: GroupAudit) -> str:
    host = audit.instance_host.split(".")[0]
    date = audit.generated_at.strftime("%Y-%m-%d")
    return f"{host}-{audit.group_name}-discovery-{date}"


def _header(audit: GroupAudit) -> str:
    meta = (
        f"Instance: {html_escape(audit.instance_host)} &nbsp;•&nbsp; groupId "
        f"{html_escape(audit.group_id)} &nbsp;•&nbsp; Generated "
        f"{audit.generated_at.strftime('%Y-%m-%d %H:%M')} by {html_escape(audit.generated_by)} "
        f"&nbsp;•&nbsp; Source: Jira Cloud REST API v3 &nbsp;•&nbsp; Internal — confidential"
    )
    return (
        f'<div class="header"><h1>{html_escape(audit.group_name)} — Group Discovery</h1>'
        f'<div class="sub">Where the {html_escape(audit.group_name)} group is used across the '
        f'{html_escape(audit.instance_host)} tenant.</div>'
        f'<div class="meta">{meta}</div></div>'
    )


def _cards(audit: GroupAudit) -> str:
    s = audit.stats
    cards = [
        stat_card(s["members"], "TOTAL MEMBERS"),
        stat_card(s["active"], "ACTIVE"),
        stat_card(s["inactive"], "INACTIVE (STILL IN GROUP)"),
        stat_card(s["permission_schemes"], "PERMISSION SCHEMES"),
        stat_card(s["projects_affected"], "PROJECTS AFFECTED"),
        stat_card(s["filters_shared"], "FILTERS SHARED"),
        stat_card(s["dashboards_shared"], "DASHBOARDS SHARED"),
        stat_card(s["license_seats"], "LICENSE SEATS GRANTED"),
    ]
    if s.get("jql_references"):
        cards.append(stat_card(s["jql_references"], "JQL REFERENCES"))
    if s.get("custom_field_refs"):
        cards.append(stat_card(s["custom_field_refs"], "CUSTOM-FIELD REFS"))
    return f'<div class="cards">{"".join(cards)}</div>'


def _summary(audit: GroupAudit) -> str:
    sm = audit.summary
    parts = [f'<div class="callout"><b>{html_escape(sm.headline)}</b></div>']
    if sm.elevated_powers:
        items = "; ".join(html_escape(p) for p in sm.elevated_powers)
        parts.append(f'<div class="callout">Elevated powers: {items}.</div>')
    if sm.hygiene_flags:
        items = "; ".join(html_escape(f) for f in sm.hygiene_flags)
        parts.append(f'<div class="callout warn"><b>Hygiene flags:</b> {items}.</div>')
    return "<h2>Executive summary</h2>" + "".join(parts)


def _app_access(audit: GroupAudit) -> str:
    rows = [[
        html_escape(r.name), html_escape(r.key),
        f"{r.seats_used} / {r.seats_total}",
        badge("yes" if r.is_member else "no", "no" if not r.is_member else "view"),
        badge("yes" if r.is_default else "no", "no" if not r.is_default else "view"),
    ] for r in audit.app_roles]
    table = section_table(["Application role", "Key", "Seats used / total", "Member?", "Default?"], rows)
    verdict = "no" if not audit.grants_license else "YES"
    return f"<h2>1. Application access (license seats)</h2>{table}<p>Result: grants license = <b>{verdict}</b>.</p>"


def _perm_schemes(audit: GroupAudit) -> str:
    rows = []
    for sch in audit.perm_schemes:
        pills = "".join(f'<span class="pill">{html_escape(p)}</span>' for p in sch.permissions)
        tag = f' <span class="tag">{html_escape(sch.bundle_tag)}</span>' if sch.bundle_tag else ""
        rows.append([str(sch.scheme_id), html_escape(sch.scheme_name) + tag, pills, str(sch.project_count)])
    table = section_table(["#", "Scheme", "Permissions granted", "Projects"], rows)
    blocks = [table, "<h2>2b. Projects affected (by scheme)</h2>"]
    for sch in audit.perm_schemes:
        refs = audit.projects_by_scheme.get(sch.scheme_id, [])
        if not refs:
            continue
        items = "".join(f"<div><b>{html_escape(p.key)}</b> · {html_escape(p.name)}</div>" for p in refs)
        blocks.append(f"<h3>#{sch.scheme_id} — {html_escape(sch.scheme_name)} ({len(refs)} projects)</h3>"
                      f'<div class="cols">{items}</div>')
    return "<h2>2. Permission schemes</h2>" + "".join(blocks)


def _filters(audit: GroupAudit) -> str:
    shared_rows = [[html_escape(f.filter_id), html_escape(f.name), html_escape(f.owner), badge(f.access, f.access)]
                   for f in audit.filters_shared]
    jql_rows = [[html_escape(j.filter_id), html_escape(j.name), html_escape(j.owner), html_escape(j.matched_clause)]
                for j in audit.filters_jql]
    out = "<h2>3. Filters shared with the group</h2>"
    out += section_table(["Filter ID", "Name", "Owner", "Access"], shared_rows) if shared_rows else "<p>None.</p>"
    out += "<h2>3b. Filters whose JQL references the group</h2>"
    out += section_table(["Filter ID", "Name", "Owner", "Matched clause"], jql_rows) if jql_rows else "<p>None.</p>"
    return out


def _dashboards(audit: GroupAudit) -> str:
    rows = [[html_escape(d.dashboard_id), html_escape(d.name), html_escape(d.owner), badge(d.access.upper() if d.access == "edit" else d.access, d.access)]
            for d in audit.dashboards_shared]
    table = section_table(["Dashboard ID", "Name", "Owner", "Access"], rows) if rows else "<p>None.</p>"
    return f"<h2>4. Dashboards shared with the group</h2>{table}"


def _other_dimensions(audit: GroupAudit) -> str:
    rows = []
    rows.append(["Notification schemes",
                 "Not used" if not audit.notification_hits else f"{len(audit.notification_hits)} scheme(s)"])
    rows.append(["Issue security schemes",
                 "Not present" if not audit.security_hits else f"{len(audit.security_hits)} scheme(s)"])
    for r in audit.role_hits:
        note = "inert migration artifact" if not r.granted_by_any_scheme else "granted by a permission scheme"
        rows.append([f"Project role #{r.role_id} {html_escape(r.role_name)}", f"default actor — {note}"])
    for c in audit.custom_field_hits:
        rows.append([f"Custom field {html_escape(c.field_name)}", html_escape(c.detail)])
    return "<h2>5. Other dimensions checked</h2>" + section_table(["Dimension", "Result"], rows)


def _membership(audit: GroupAudit) -> str:
    out = ["<h2>6. Membership roster</h2>"]
    if audit.inactive_in_group:
        names = ", ".join(html_escape(m.display_name) for m in audit.inactive_in_group)
        out.append(f'<div class="callout warn"><b>Inactive accounts still in group:</b> {names}</div>')
    if audit.non_human:
        names = ", ".join(html_escape(m.display_name) for m in audit.non_human)
        out.append(f'<div class="callout"><b>Bot / service / test accounts:</b> {names}</div>')
    items = []
    for m in audit.members:
        flag = ' <span class="badge-edit">inactive</span>' if not m.active else ""
        items.append(f"<div>{html_escape(m.display_name)}{flag}</div>")
    out.append(f'<div class="cols">{"".join(items)}</div>')
    return "".join(out)


def _manual_checks(audit: GroupAudit) -> str:
    rows = [[html_escape(c.dimension), html_escape(c.reason), html_escape(c.ui_path)] for c in audit.manual_checks]
    note = ""
    if audit.incomplete_dimensions:
        note = (f'<div class="callout warn">Some dimensions could not be fully read this run: '
                f'{html_escape(", ".join(audit.incomplete_dimensions))}. Treat them as unverified.</div>')
    return ("<h2>7. Manual check required (no public Cloud REST read)</h2>" + note
            + section_table(["Dimension", "Why", "Where to verify"], rows))


def _footnote() -> str:
    return ('<div class="footnote">Generated read-only via Jira Cloud REST API v3 (HTTP Basic). '
            'Global permissions, automation, and workflow conditions have no public REST read endpoint '
            'and must be verified in the UI.</div>')


def build_html(audit: GroupAudit) -> str:
    body = "".join([
        _header(audit), _cards(audit), _summary(audit), _app_access(audit),
        _perm_schemes(audit), _filters(audit), _dashboards(audit),
        _other_dimensions(audit), _membership(audit), _manual_checks(audit), _footnote(),
    ])
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"


def render(audit: GroupAudit, out_dir) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = output_basename(audit)
    pdf_path = out_dir / f"{base}.pdf"
    json_path = out_dir / f"{base}.json"
    HTML(string=build_html(audit)).write_pdf(str(pdf_path))
    json_path.write_text(json.dumps(audit_to_dict(audit), indent=2))
    return pdf_path, json_path
