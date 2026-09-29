from __future__ import annotations

import re
from pathlib import Path

import release_info

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
CORE_JS = (ROOT / "static" / "js" / "dpe.js").read_text(encoding="utf-8")
TEACHING_JS = (ROOT / "static" / "js" / "dpe_cost_teaching.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "css" / "dpe.css").read_text(encoding="utf-8")
DPE_JS_FILES = sorted((ROOT / "static" / "js").glob("dpe*.js"))


def test_skip_link_main_landmark_and_busy_status_are_accessible():
    assert 'class="dpe-skip-link" href="#dpeMainContent"' in TEMPLATE
    assert 'id="dpeMainContent" tabindex="-1"' in TEMPLATE
    assert 'id="dpeBusyStatus"' in TEMPLATE
    assert 'role="status"' in TEMPLATE
    assert 'aria-live="polite"' in TEMPLATE
    assert 'id="dpeAlert"' in TEMPLATE and 'tabindex="-1"' in TEMPLATE


def test_every_dpe_modal_exposes_state_and_the_critical_dialog_is_described():
    modal_ids = (
        "managementModal",
        "costEngineModal",
        "dpeConfirmModal",
    )
    for modal_id in modal_ids:
        opening = re.search(rf'<div[^>]+id="{modal_id}"[^>]*>', TEMPLATE)
        assert opening, f"Modal {modal_id} nao encontrado"
        assert 'aria-hidden="true"' in opening.group(0), modal_id
    confirm = re.search(r'<div[^>]+id="dpeConfirmModal"[^>]*>', TEMPLATE)
    assert confirm and 'role="alertdialog"' in confirm.group(0)
    assert 'aria-labelledby="dpeConfirmTitle"' in confirm.group(0)
    assert 'aria-describedby="dpeConfirmMessage"' in confirm.group(0)
    assert 'id="dpeConfirmReason"' in TEMPLATE
    assert 'id="dpeConfirmError"' in TEMPLATE


def test_legacy_frontend_is_not_loaded_or_exposed():
    assert 'dpe_finance.js' not in TEMPLATE
    assert 'dpe-legacy-nav' not in TEMPLATE
    for section in ("receitas", "despesas", "cursos", "dpe01", "dpe02", "dpe03", "arquivos"):
        assert f'id="section-{section}"' not in TEMPLATE
    for modal_id in ("measurementModal", "importModal", "financeModal"):
        assert f'id="{modal_id}"' not in TEMPLATE
    assert not (ROOT / "static" / "js" / "dpe_finance.js").exists()
    assert "ensureLegacyLoaded" not in CORE_JS


def test_raw_browser_confirm_and_prompt_are_not_used_by_dpe_frontend():
    forbidden = re.compile(r"\b(?:confirm|prompt)\s*\(")
    offenders = []
    for path in DPE_JS_FILES:
        if forbidden.search(path.read_text(encoding="utf-8")):
            offenders.append(path.name)
    assert offenders == []


def test_global_modal_helpers_manage_focus_keyboard_and_busy_state():
    expected_tokens = (
        "function openDPEModal",
        "function closeDPEModal",
        "function trapModalFocus",
        "function bindAccessibleTabs",
        "function requestDPEConfirmation",
        "function focusInlineError",
        "function dpeEmptyState",
        "setAttribute('aria-busy'",
        "event.key!=='Escape'",
        "event.key!=='Tab'",
    )
    for token in expected_tokens:
        assert token in CORE_JS, token


def test_combobox_and_tabs_have_keyboard_accessibility_contracts():
    assert "aria-controls" in TEACHING_JS
    assert "aria-haspopup" in TEACHING_JS
    assert "aria-activedescendant" in TEACHING_JS
    assert "ArrowDown" in TEACHING_JS and "ArrowUp" in TEACHING_JS
    assert "aria-selected" in TEACHING_JS
    assert "ArrowRight" in CORE_JS and "ArrowLeft" in CORE_JS
    assert "Home" in CORE_JS and "End" in CORE_JS


def test_styles_include_refined_states_tooltips_focus_and_responsive_rules():
    expected_tokens = (
        ".dpe-skip-link",
        ".dpe-busy-status",
        ".dpe-empty-state",
        ".dpe-help-tip",
        ".dpe-confirm-card",
        ":focus-visible",
        "prefers-reduced-motion",
        "max-width:720px",
    )
    compact_css = CSS.replace(" ", "")
    for token in expected_tokens:
        haystack = compact_css if token == "max-width:720px" else CSS
        assert token in haystack, token


def test_frontend_cleanup_remains_active_after_backend_retirement():
    assert release_info.APP_VERSION.startswith("0.13.0")
    assert release_info.SCHEMA_VERSION >= 43
    assert (ROOT / "database" / "043_dpe_legacy_backend_retirement_v0130.sql").exists()
