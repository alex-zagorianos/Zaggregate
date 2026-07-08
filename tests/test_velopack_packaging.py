"""Unit tests for the Velopack packaging argv (src/build_package.py).

`vpk` is a .NET tool that is not installed on most dev boxes or in this test
environment, so we cannot run a real pack here. What we CAN pin — and what actually
breaks releases when it drifts — is the argv build_package hands to vpk: the pack id
an installed app is bound to, the channel, and (the subtle one) the SemVer a beta
prerelease packs under.
"""
import build_package as bp


def test_pack_id_and_main_exe_are_stable():
    """The pack id names the install root and binds every installed app to its feed;
    it must never change silently. A test failure here is a loud 'are you SURE?'."""
    assert bp.VELOPACK_PACK_ID == "Zaggregate"
    assert bp.VELOPACK_MAIN_EXE == "JobProgram.exe"


def test_argv_defaults_to_app_version_on_the_win_channel():
    argv = bp.vpk_pack_argv()
    assert argv[:2] == ["vpk", "pack"]
    d = dict(zip(argv[2::2], argv[3::2]))
    assert d["--packId"] == "Zaggregate"
    assert d["--packVersion"] == bp.APP_VERSION
    assert d["--mainExe"] == "JobProgram.exe"
    assert d["--channel"] == "win"


def test_beta_prerelease_packs_under_the_full_prerelease_version():
    """v1.0.3-beta1 must pack as 1.0.3-beta1, NOT 1.0.3 — SemVer sorts the prerelease
    below the release, which is what keeps a beta tester ahead of stable and lets the
    eventual 1.0.3 carry them forward."""
    argv = bp.vpk_pack_argv("beta", pack_version="v1.0.3-beta1")
    d = dict(zip(argv[2::2], argv[3::2]))
    assert d["--channel"] == "beta"
    assert d["--packVersion"] == "1.0.3-beta1"


def test_leading_v_is_stripped():
    assert bp._normalize_pack_version("v2.0.0") == "2.0.0"
    assert bp._normalize_pack_version("2.0.0") == "2.0.0"
    assert bp._normalize_pack_version(None) == bp.APP_VERSION


def test_unknown_channel_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        bp.vpk_pack_argv("stable")   # not one of ('win', 'beta')


def test_both_shipped_channels_are_packable():
    for ch in bp.VELOPACK_CHANNELS:
        argv = bp.vpk_pack_argv(ch)
        assert "--channel" in argv and ch in argv
