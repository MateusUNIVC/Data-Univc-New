from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")


def test_course_chart_labels_are_not_limited_to_two_lines():
    assert "function wrapChartLabel(value, maxChars = 28, maxLines = Infinity)" in APP_JS
    assert "wrapChartLabel(item.curso, maxLabelChars)" in APP_JS
    assert "wrapChartLabel(item?.curso, maxChars, 2)" not in APP_JS


def test_course_chart_row_height_grows_with_wrapped_label():
    assert "lines.length * 12 + 18" in APP_JS
    assert "rowHeights" in APP_JS
    assert "rowTops" in APP_JS


def test_course_chart_preserves_full_name_for_native_and_custom_tooltips():
    assert "<title>${escapeHtml(item?.curso || '—')}</title>" in APP_JS
    assert "point.curso || ''" in APP_JS
