"""Wave 6a - tracker write endpoints reject foreign-origin POSTs (CSRF)."""
import pytest
import tracker.app as tapp


@pytest.fixture
def client():
    tapp.app.config["TESTING"] = True
    return tapp.app.test_client()


def test_foreign_origin_post_is_forbidden(client):
    r = client.post("/delete/1", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_loopback_origin_post_not_forbidden(client):
    r = client.post("/delete/999999", headers={"Origin": "http://localhost:5001"})
    assert r.status_code != 403  # (redirect/200 - the guard let it through)


def test_extension_origin_api_add_not_forbidden(client):
    r = client.post("/api/add", json={"title": "T", "company": "C"},
                    headers={"Origin": "chrome-extension://abcdef"})
    assert r.status_code != 403


def test_no_origin_not_forbidden(client):
    r = client.post("/delete/999999")
    assert r.status_code != 403
