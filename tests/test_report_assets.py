from report_assets import CSS, html_escape, stat_card, section_table, badge


def test_css_has_page_footer_and_header():
    assert "@page" in CSS
    assert "counter(page)" in CSS
    assert ".header" in CSS


def test_html_escape():
    assert html_escape('a & "b" <c>') == "a &amp; &quot;b&quot; &lt;c&gt;"


def test_stat_card_renders_value_and_label():
    out = stat_card(195, "TOTAL MEMBERS")
    assert "195" in out and "TOTAL MEMBERS" in out


def test_section_table_headers_and_rows():
    out = section_table(["A", "B"], [["1", "2"], ["3", "4"]])
    assert "<th>A</th>" in out
    assert "<td>3</td>" in out


def test_badge_variants():
    assert "badge-edit" in badge("EDIT", "edit")
    assert "badge-view" in badge("view", "view")
