from scrape.xml_safe import _safe_fromstring

def test_parses_benign_xml():
    root = _safe_fromstring("<root><a>hi</a></root>")
    assert root.find("a").text == "hi"

def test_accepts_bytes():
    root = _safe_fromstring(b"<root><a>hi</a></root>")
    assert root.tag == "root"

def test_billion_laughs_is_neutralized():
    # Classic entity-expansion bomb. Either the parser refuses the DTD/entity
    # (defusedxml raises) or the DTD is stripped so &lol; never expands.
    bomb = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]>'
        '<lolz>&lol2;</lolz>'
    )
    try:
        root = _safe_fromstring(bomb)
    except Exception:
        return  # defusedxml refused it — safe
    assert "lollollol" not in (root.text or "")  # stdlib path: DTD stripped, unexpanded

def test_external_entity_not_resolved():
    xxe = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<foo>&xxe;</foo>'
    )
    try:
        root = _safe_fromstring(xxe)
    except Exception:
        return  # refused — safe
    assert "root:" not in (root.text or "")  # file contents never injected
