"""
CORS tests for the frontend -> backend connection.

Verifies that the backend allows the localhost dev origins AND the production
Vercel frontend origin (https://stock-portfolio-frontend-tau.vercel.app),
that origins are parsed safely (strip / dedupe / ignore-empty / reject "*"),
and that the actual CORSMiddleware config responds correctly to a preflight.

These tests intentionally do NOT depend on the local developer's .env file,
so they exercise the shipped code defaults that apply on Render.
"""
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import Settings, ALWAYS_ALLOWED_CORS_ORIGINS
from app.main import _parse_cors_origins

VERCEL_ORIGIN = "https://stock-portfolio-frontend-tau.vercel.app"
LOCALHOST_ORIGIN = "http://localhost:3000"
LOOPBACK_ORIGIN = "http://127.0.0.1:3000"


def _effective_origins(cors_origins: str = "") -> list:
    """Effective origins = always-allowed set merged with CORS_ORIGINS."""
    settings = Settings(_env_file=None, CORS_ORIGINS=cors_origins)
    return _parse_cors_origins(
        ",".join(list(ALWAYS_ALLOWED_CORS_ORIGINS) + [settings.CORS_ORIGINS])
    )


class TestAllowlistedOrigins:
    """The always-allowed set must include localhost + production Vercel."""

    def test_all_required_origins_present(self):
        origins = _effective_origins()
        assert LOCALHOST_ORIGIN in origins
        assert LOOPBACK_ORIGIN in origins
        assert VERCEL_ORIGIN in origins

    def test_backend_url_is_not_a_cors_origin(self):
        origins = _effective_origins()
        assert "https://stock-portfolio1.onrender.com" not in origins
        for o in origins:
            # every origin must be a browser/frontend origin (http/https),
            # never a wildcard
            assert o.startswith("http://") or o.startswith("https://")

    def test_vercel_origin_allowed_even_when_env_overrides(self):
        # Even if Render sets CORS_ORIGINS to a custom/restricted list, the
        # production Vercel frontend (in the always-allowed set) must still be
        # allowed. This is what makes the fix work purely from code.
        origins = _effective_origins("http://localhost:3000")
        assert VERCEL_ORIGIN in origins

    def test_custom_env_origins_are_merged(self):
        origins = _effective_origins("https://staging.example.com, http://192.168.1.50:3000")
        assert "https://staging.example.com" in origins
        assert "http://192.168.1.50:3000" in origins


class TestParseOrigins:
    """The origin parser must be safe and defensive."""

    def test_strips_whitespace(self):
        assert _parse_cors_origins(" http://a , http://b ") == ["http://a", "http://b"]

    def test_ignores_empty_entries(self):
        assert _parse_cors_origins("http://a,, ,http://b") == ["http://a", "http://b"]
        assert _parse_cors_origins(" , , ") == []

    def test_deduplicates_preserving_order(self):
        assert _parse_cors_origins("http://a,http://b,http://a,http://a,http://b") == [
            "http://a",
            "http://b",
        ]

    def test_rejects_wildcard(self):
        with pytest.raises(ValueError):
            _parse_cors_origins("*")
        with pytest.raises(ValueError):
            _parse_cors_origins("http://a,*,http://b")


class TestCorsMiddlewareBehavior:
    """End-to-end preflight through the actual CORSMiddleware config."""

    @pytest.fixture
    def client(self):
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_effective_origins(),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/health")
        def health():
            return {"ok": True}

        return TestClient(app)

    def test_vercel_origin_preflight_allowed(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": VERCEL_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        allow = resp.headers.get("access-control-allow-origin")
        assert allow == VERCEL_ORIGIN
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_localhost_origin_preflight_allowed(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": LOCALHOST_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == LOCALHOST_ORIGIN

    def test_disallowed_origin_rejected(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Starlette omits the allow-origin header for disallowed origins
        assert "access-control-allow-origin" not in resp.headers
