from __future__ import annotations

CSS = """
@page {
  size: A4; margin: 1.6cm 1.4cm 2cm 1.4cm;
  @bottom-left { content: "Jira Group Auditor — " string(doctitle); font-size: 8pt; color: #9aa5b1; }
  @bottom-right { content: "Page " counter(page) " / " counter(pages); font-size: 8pt; color: #9aa5b1; }
}
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1f2933; font-size: 10.5pt; }
h1 { string-set: doctitle content(); }
.header { background: linear-gradient(135deg, #1c3d6e, #2a5298); color: #fff; padding: 22px 24px; border-radius: 8px; }
.header h1 { margin: 0 0 6px; font-size: 24pt; }
.header .sub { font-size: 11pt; opacity: 0.95; }
.header .meta { font-size: 8.5pt; opacity: 0.85; margin-top: 10px; }
.cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
.card { flex: 1 1 30%; border: 1px solid #e4e7eb; border-radius: 8px; padding: 12px 14px; }
.card .value { font-size: 22pt; font-weight: 700; color: #2a5298; }
.card .label { font-size: 8pt; letter-spacing: 0.04em; color: #7b8794; text-transform: uppercase; }
h2 { font-size: 14pt; border-bottom: 2px solid #2a5298; padding-bottom: 4px; margin-top: 26px; }
.callout { border-left: 4px solid #2a5298; background: #f5f7fa; padding: 10px 14px; margin: 8px 0; font-size: 10pt; }
.callout.warn { border-left-color: #de911d; background: #fdf6e3; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9pt; }
th { background: #1f2933; color: #fff; text-align: left; padding: 6px 8px; }
td { border-bottom: 1px solid #eceff1; padding: 5px 8px; vertical-align: top; }
.pill { display: inline-block; background: #eef2f7; border: 1px solid #d2dae6; border-radius: 10px; padding: 1px 8px; margin: 1px; font-size: 8pt; }
.tag { display: inline-block; background: #fdf0d5; color: #8a6d1b; border-radius: 4px; padding: 1px 6px; font-size: 8pt; }
.badge-view { background: #e6f0ff; color: #2a5298; border-radius: 4px; padding: 1px 6px; font-size: 8pt; }
.badge-edit { background: #fde2e1; color: #b3261e; border-radius: 4px; padding: 1px 6px; font-size: 8pt; font-weight: 600; }
.badge-no { background: #e3f4e8; color: #1a7f37; border-radius: 4px; padding: 1px 6px; font-size: 8pt; }
.cols { column-count: 3; column-gap: 16px; font-size: 8.5pt; }
.footnote { color: #7b8794; font-size: 8pt; margin-top: 24px; }
"""


def html_escape(text: object) -> str:
    s = str(text)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def stat_card(value: object, label: str) -> str:
    return f'<div class="card"><div class="value">{html_escape(value)}</div><div class="label">{html_escape(label)}</div></div>'


def badge(text: str, variant: str) -> str:
    cls = {"edit": "badge-edit", "view": "badge-view", "no": "badge-no"}.get(variant, "badge-view")
    return f'<span class="{cls}">{html_escape(text)}</span>'


def section_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html_escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
