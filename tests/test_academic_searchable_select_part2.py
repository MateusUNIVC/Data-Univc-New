from __future__ import annotations

import unittest
from pathlib import Path


class AcademicSearchableSelectPart2Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.html = (self.root / "templates" / "index.html").read_text(encoding="utf-8")
        self.app_js = (self.root / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.shared_js = (self.root / "static" / "js" / "data-univc-ui.js").read_text(encoding="utf-8")
        self.shared_css = (self.root / "static" / "css" / "data-univc-foundation.css").read_text(encoding="utf-8")

    def test_dashboard_and_results_disciplines_are_searchable(self):
        self.assertIn('id="dashboardDiscipline" data-combobox-placeholder="Pesquisar disciplina..."', self.html)
        self.assertIn('id="resultsDisciplineFilter" data-combobox-placeholder="Pesquisar disciplina..."', self.html)
        self.assertGreaterEqual(self.app_js.count("DataUNIVC?.searchableSelect?.attach(select)"), 2)

    def test_component_keeps_native_select_as_source_of_truth(self):
        self.assertIn("select.dispatchEvent(new Event('change', {bubbles:true}))", self.shared_js)
        self.assertIn("select.value = button.dataset.comboboxValue", self.shared_js)
        self.assertIn("select.classList.add('du-combobox-native-hidden')", self.shared_js)

    def test_search_is_accent_insensitive_and_keyboard_accessible(self):
        self.assertIn(".normalize('NFD')", self.shared_js)
        self.assertIn(r"/[\u0300-\u036f]/g", self.shared_js)
        self.assertIn("event.key === 'ArrowDown'", self.shared_js)
        self.assertIn("event.key === 'ArrowUp'", self.shared_js)
        self.assertIn("event.key === 'Enter'", self.shared_js)
        self.assertIn("event.key === 'Escape'", self.shared_js)

    def test_shared_styles_support_long_labels_and_mobile(self):
        self.assertIn("overflow-wrap:anywhere", self.shared_css)
        self.assertIn("max-height:min(300px,42vh)", self.shared_css)
        self.assertIn("@media(max-width:760px)", self.shared_css)

    def test_index_assets_use_build_fingerprint_for_cache_busting(self):
        app_py = (self.root / "app.py").read_text(encoding="utf-8")
        self.assertIn('"asset_version": f"{APP_VERSION}-{BUILD_FINGERPRINT}"', app_py)
        self.assertIn('?v={{ asset_version }}', self.html)
        self.assertNotIn('?v={{ app_version }}', self.html)


if __name__ == "__main__":
    unittest.main()
