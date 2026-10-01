from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_surface_prioritizes_users_and_links_to_academic_page():
    html=(ROOT/'templates'/'reitoria.html').read_text(encoding='utf-8')
    js=(ROOT/'static'/'js'/'admin_users.js').read_text(encoding='utf-8')
    assert 'data-admin-nav="usuarios"' in html
    assert 'class="reitoria-nav-item active" data-admin-nav="usuarios"' in html
    assert 'href="/reitoria/academico"' in html
    assert "get('secao') || 'usuarios'" in js
    assert 'reitoria_academic.js' not in html
    assert 'reitoria_academico.js' not in html


def test_academic_surface_uses_academic_design_system_not_reitoria_admin_css():
    html=(ROOT/'templates'/'reitoria_academico.html').read_text(encoding='utf-8')
    assert '/static/css/app.css' in html
    assert '/static/css/ui-v2.css' in html
    assert '/static/css/reitoria-academico.css' in html
    assert '/static/css/reitoria.css' not in html
    assert 'class="ui-v2 ui-v2-academic reitoria-academic-app"' in html
    assert 'class="sidebar"' in html
    assert 'class="main-content"' in html
    assert 'class="analysis-bar reitoria-global-filters"' in html


def test_academic_surface_remains_reitoria_only():
    router=(ROOT/'admin_router.py').read_text(encoding='utf-8')
    block=router.split('@router.get("/reitoria/academico"',1)[1].split('@router.get("/admin/users"',1)[0]
    assert 'Depends(require_fresh_reitoria)' in block
    assert 'reitoria_academico.html' in block


def test_old_admin_users_url_redirects_to_reitoria():
    router=(ROOT/'admin_router.py').read_text(encoding='utf-8')
    block=router.split('@router.get("/admin/users")',1)[1].split('@router.get("/api/admin/users")',1)[0]
    assert 'RedirectResponse(url="/reitoria", status_code=307)' in block
