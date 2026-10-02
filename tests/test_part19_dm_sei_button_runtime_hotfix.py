from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dm_sei_entry_buttons_reference_live_modal_contract():
    js = (ROOT / "static/js/dm.js").read_text(encoding="utf-8")
    html = (ROOT / "templates/dm.html").read_text(encoding="utf-8")
    router = (ROOT / "dm_router.py").read_text(encoding="utf-8")

    assert 'id="seiDirectButton"' in html
    assert 'id="seiUploadButton"' in html
    assert "$('#seiDirectButton')?.addEventListener('click',()=>openSeiModal('direct'))" in js
    assert "$('#seiUploadButton')?.addEventListener('click',()=>openSeiModal('upload'))" in js
    assert "openModal('seiModal');" in js
    assert "seiCheckDatesWrap" not in js
    assert 'DM_ASSET_VERSION = f"{APP_VERSION}-dmexcel03b"' in router


def test_dm_unguarded_direct_id_references_exist_in_template():
    js = (ROOT / "static/js/dm.js").read_text(encoding="utf-8")
    html = (ROOT / "templates/dm.html").read_text(encoding="utf-8")

    template_ids = set(re.findall(r'''id=["']([^"']+)["']''', html))
    direct_refs = re.findall(
        r'''\$\(["']#([A-Za-z0-9_-]+)["']\)\.([A-Za-z_$][\w$]*)''',
        js,
    )
    missing = sorted({element_id for element_id, _ in direct_refs if element_id not in template_ids})
    assert missing == []
