from pathlib import Path
import release_info

ROOT = Path(__file__).resolve().parents[1]

def test_production_release_metadata():
    assert release_info.APP_VERSION == "0.13.0"
    assert release_info.SCHEMA_VERSION == 49
    assert release_info.SCHEMA_MIGRATION == "049_academic_faculty_context_scopes_v0130.sql"

def test_production_examples_are_hardened():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ENVIRONMENT=production" in env
    assert "AUTH_DISABLED=false" in env
    assert "COOKIE_SECURE=true" in env
    assert "REQUIRE_SCHEMA_VERSION=true" in env
    assert "LOGIN_RATE_LIMIT_ENABLED=true" in env
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "LOGIN_RATE_LIMIT_ENABLED" in render
    assert 'value: "true"' in render

def test_production_release_document_exists():
    assert (ROOT / "docs/PRODUCTION_RELEASE_v0130.md").exists()
