# Scraping Sources

#phase1 #scraper #apis

## Active Sources

### Adzuna ✅ WORKING
- **Type:** REST API
- **Cost:** Free — 2,500 req/month
- **Coverage:** General job board, good US coverage
- **Results per page:** 50
- **Rate limit:** 25 req/min
- **Auth:** `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` in `.env`
- **Docs:** https://developer.adzuna.com/

### JSearch (RapidAPI) ⏳ KEY NEEDED
- **Type:** REST API via RapidAPI
- **Cost:** Free — **200 req/MONTH** (conserve carefully — ~10 full runs/month with 10 keywords × 1 page)
- **Coverage:** Aggregates Indeed + LinkedIn + Glassdoor — biggest coverage boost
- **Results per page:** 10
- **Rate limit:** 5 req/min (self-imposed to protect monthly budget)
- **Auth:** `JSEARCH_RAPIDAPI_KEY` in `.env`
- **Get key:** https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
- **⚠️ Use `--max-pages 1` for JSearch to conserve budget**

### USAJobs ⏳ KEY NEEDED
- **Type:** REST API (federal government)
- **Cost:** Free — generous limits
- **Coverage:** Federal jobs only — relevant for GE Aerospace, AFRL (Wright-Patt), DoD contracts near Cincinnati
- **Results per page:** 25
- **Rate limit:** 50 req/min
- **Auth:** `USAJOBS_API_KEY` + `USAJOBS_USER_AGENT` (your email) in `.env`
- **Register:** https://developer.usajobs.gov/
- **Location note:** Must use `"Cincinnati, OH"` format (state required)

## Evaluated But Not Added

| Source | Reason skipped |
|---|---|
| LinkedIn direct scrape | Actively blocks, ToS risk, JSearch covers it |
| Indeed RSS | JSearch covers Indeed with better structure |
| Glassdoor | JSearch covers it |
| iHireEngineering | Possible future addition for niche engineering roles |
| Dice | Possible future addition for controls/embedded overlap |

## Adding a New Source

1. Create `search/newclient.py` inheriting `JobAPIClient`
2. Implement `search()` and `parse_results()`
3. Add config constants to `config.py`
4. Add env vars to `.env.example`
5. Add to `build_clients()` in `search/cli.py`
