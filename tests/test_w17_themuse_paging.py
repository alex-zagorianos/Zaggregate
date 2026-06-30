"""Wave (F17) — keyword-blind feeds keep paging until the RAW feed is spent."""
from search.search_engine import SearchEngine


class _BlindFeed:
    """Mimics The Muse: raw pages have data but a keyword can match 0 on a page;
    sets _raw_exhausted when the raw feed ends."""
    def __init__(self):
        self.seen = []
        self._raw_exhausted = False

    def search_and_parse(self, keyword, location, salary_min, page):
        self.seen.append(page)
        self._raw_exhausted = page >= 3
        return []


class _NormalFeed:
    def __init__(self):
        self.seen = []

    def search_and_parse(self, keyword, location, salary_min, page):
        self.seen.append(page)
        return []


def test_keyword_blind_feed_pages_until_raw_exhausted():
    c = _BlindFeed()
    SearchEngine([c])._run_client(c, ["controls"], "Cincinnati", None, 5)
    assert c.seen == [1, 2, 3]  # kept paging past empty pages, stopped at raw end


def test_normal_feed_stops_on_first_empty():
    c = _NormalFeed()
    SearchEngine([c])._run_client(c, ["x"], "Cincinnati", None, 5)
    assert c.seen == [1]  # no _raw_exhausted -> default behavior (stop on empty)
