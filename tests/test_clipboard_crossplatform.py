import claude_bridge


def test_to_clipboard_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(claude_bridge.sys, "platform", "win32")
    monkeypatch.setattr(claude_bridge.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(claude_bridge.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd))
    assert claude_bridge.to_clipboard("hi") is True
    assert calls[0] == "clip"


def test_to_clipboard_macos(monkeypatch):
    calls = []
    monkeypatch.setattr(claude_bridge.sys, "platform", "darwin")
    monkeypatch.setattr(claude_bridge.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd))
    assert claude_bridge.to_clipboard("hi") is True
    assert ["pbcopy"] in calls


def test_to_clipboard_linux_fallback(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == "xclip":
            raise FileNotFoundError
        return None

    monkeypatch.setattr(claude_bridge.sys, "platform", "linux")
    monkeypatch.setattr(claude_bridge.subprocess, "run", fake_run)
    assert claude_bridge.to_clipboard("hi") is True
    assert ["xsel", "--clipboard", "--input"] in calls


def test_to_clipboard_all_fail(monkeypatch):
    monkeypatch.setattr(claude_bridge.sys, "platform", "linux")

    def boom(cmd, **kw):
        raise FileNotFoundError

    monkeypatch.setattr(claude_bridge.subprocess, "run", boom)
    assert claude_bridge.to_clipboard("hi") is False
