"""FileCache must map ANY client key to a legal filename on Windows.

Regression: JobicyClient caches under the key "feed:<industry>". A ':' in a
filename makes NTFS treat it as an alternate-data-stream path, so the atomic
write's os.replace failed with WinError 87 and the feed ran uncached forever
(live daily_run 2026-07-01). FileCache now sanitizes illegal characters.
"""
import pytest

from search.http_util import FileCache


@pytest.mark.parametrize("key", [
    "feed:engineering",            # the live jobicy failure
    'a<b>c:"d/e\\f|g?h*i',         # every illegal character at once
])
def test_unsafe_keys_round_trip(tmp_path, key):
    cache = FileCache("src", cache_dir=tmp_path)
    cache.put(key, {"jobs": [1, 2]})
    assert cache.get(key) == {"jobs": [1, 2]}


def test_sanitized_name_stays_in_subdir(tmp_path):
    cache = FileCache("src", cache_dir=tmp_path)
    cache.put("feed:engineering", {"ok": True})
    files = list((tmp_path / "src").iterdir())
    assert [f.name for f in files] == ["feed_engineering.json"]
