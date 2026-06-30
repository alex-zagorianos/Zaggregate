"""Wave 6b — SSRF guard on the discovery domain fetcher."""
import socket
import discover.career_link as cl


def _addrinfo(ip):
    return [(socket.AF_INET, None, None, "", (ip, 0))]


def test_url_ok_rejects_non_http():
    assert cl._url_ok("ftp://example.com") is False
    assert cl._url_ok("file:///etc/passwd") is False
    assert cl._url_ok("not a url") is False


def test_url_ok_rejects_private_loopback_linklocal(monkeypatch):
    for ip in ("169.254.169.254", "10.0.0.5", "127.0.0.1", "192.168.1.1"):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, _ip=ip, **k: _addrinfo(_ip))
        assert cl._url_ok("http://whatever/") is False


def test_url_ok_allows_public(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    assert cl._url_ok("https://example.com/careers") is True


def test_get_blocks_private_without_network(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("127.0.0.1"))

    def _boom(*a, **k):
        raise AssertionError("network must not be called for a private host")

    monkeypatch.setattr(cl, "make_session", _boom)
    assert cl._get("http://localhost/robots.txt") is None
