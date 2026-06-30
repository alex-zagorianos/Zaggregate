"""Unit tests for the safe_url helper in gui.py.

safe_url must only pass http(s) URLs; javascript:/data:/file:/empty must be
rejected (returns empty string) so webbrowser.open is never called on them.
"""
from gui import safe_url


def test_http_passes():
    url = "http://example.com/jobs/123"
    assert safe_url(url) == url


def test_https_passes():
    url = "https://boards.greenhouse.io/acme/jobs/1"
    assert safe_url(url) == url


def test_javascript_rejected():
    assert safe_url("javascript:alert(document.cookie)") == ""


def test_data_rejected():
    assert safe_url("data:text/html,<script>alert(1)</script>") == ""


def test_file_rejected():
    assert safe_url("file:///etc/passwd") == ""


def test_empty_string_rejected():
    assert safe_url("") == ""


def test_none_rejected():
    assert safe_url(None) == ""


def test_ftp_rejected():
    assert safe_url("ftp://ftp.example.com/file.txt") == ""


def test_bare_path_rejected():
    assert safe_url("/relative/path") == ""


def test_malformed_still_safe():
    # urlparse does not raise; scheme is '' -> rejected
    assert safe_url("not-a-url-at-all") == ""
