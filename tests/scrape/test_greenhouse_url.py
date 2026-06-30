from scrape.greenhouse_url import embed_url, parse


def test_embed_url_builds_server_rendered_application_link():
    assert embed_url("nuro", 6916236) == (
        "https://job-boards.greenhouse.io/embed/job_app?for=nuro&token=6916236"
    )
    # token may arrive as a string
    assert embed_url("tulip", "7710246003").endswith("for=tulip&token=7710246003")


def test_parse_embed_url():
    assert parse(
        "https://job-boards.greenhouse.io/embed/job_app?for=nuro&token=6916236"
    ) == ("nuro", "6916236")


def test_parse_hosted_board_path():
    assert parse("https://boards.greenhouse.io/acme/jobs/123") == ("acme", "123")
    assert parse(
        "https://job-boards.greenhouse.io/acme/jobs/123?utm_medium=z"
    ) == ("acme", "123")


def test_parse_company_embed_gh_jid_has_token_but_no_slug():
    # The broken company-SPA link: id is recoverable, slug is not.
    assert parse("https://nuro.ai/careersitem?gh_jid=6916236") == (None, "6916236")
    assert parse("https://tulip.co/careers/job-posting/?gh_jid=7710246003") == (
        None, "7710246003",
    )


def test_parse_rejects_non_greenhouse():
    assert parse("https://jobs.lever.co/acme/a1b2") is None
    assert parse("https://jobs.ashbyhq.com/acme/uuid") is None
    assert parse("") is None
    assert parse("https://example.com/careers") is None
