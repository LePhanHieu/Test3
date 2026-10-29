"""HTTP-rendering smoke tests; these do not replace real-browser responsive QA."""

import importlib

from test_api_auth_isolation import _csrf

pytest_plugins = ["test_api_auth_isolation"]


def test_real_app_renders_homepage_and_protects_role_portals(isolated_app):
    webapp = importlib.import_module("skin_cancer.webapp.app")
    client = webapp.app.test_client()

    homepage = client.get("/")
    assert homepage.status_code == 200
    assert b"DermaScan AI" in homepage.data
    assert b'id="hpOpenLoginBtn"' in homepage.data
    assert client.get("/doctor").status_code == 401
    assert client.get("/patient").status_code == 401
    assert client.get("/admin").status_code == 401

    result = client.post(
        "/api/auth/login",
        headers=_csrf(client),
        json={"email": "synthetic-user@example.invalid", "password": "qa-password-1234"},
    )
    assert result.status_code == 200
    assert client.get("/patient").status_code == 200
    assert client.get("/doctor").status_code == 403
    assert client.get("/admin").status_code == 403
