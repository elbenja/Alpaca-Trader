"""
Form 4 Fetcher — Scrapes OpenInsider for recent insider open-market purchases,
cross-references against the current S&P 500 list, and returns qualifying buys.

Strict filter rules (enforced in code, not left to the LLM):
- Open-market purchases only (transaction code "P")
- Total dollar value >= $200,000
- Issuer must be in the current S&P 500

Data sources:
- OpenInsider screener (http://openinsider.com) — purchases filtered by filing date
- Wikipedia List_of_S&P_500_companies — authoritative constituent list, cached locally
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

OPENINSIDER_URL = "http://openinsider.com/screener"
WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

SP500_CACHE_PATH = os.path.join(OUTPUT_DIR, "sp500_cache.json")
SP500_CACHE_TTL_DAYS = 7

MIN_PURCHASE_VALUE = 200_000
DEFAULT_LOOKBACK_DAYS = 3  # Covers weekends/holidays for filings "since last trading day"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_sp500_tickers(force_refresh: bool = False) -> set:
    """
    Return the current S&P 500 tickers as a set. Cached locally for 7 days.
    Tickers are normalized to use '.' as separator (e.g., BRK.B, not BRK-B).
    """
    if not force_refresh and _sp500_cache_is_fresh():
        try:
            with open(SP500_CACHE_PATH, "r") as f:
                return set(json.load(f)["tickers"])
        except Exception as e:
            logger.warning(f"S&P 500 cache read failed, refetching: {e}")

    tickers = _fetch_sp500_from_wikipedia()
    if tickers:
        try:
            with open(SP500_CACHE_PATH, "w") as f:
                json.dump({"tickers": sorted(tickers), "fetched_at": datetime.now(timezone.utc).isoformat()}, f)
        except Exception as e:
            logger.warning(f"S&P 500 cache write failed: {e}")
    return tickers


def _sp500_cache_is_fresh() -> bool:
    if not os.path.exists(SP500_CACHE_PATH):
        return False
    age_seconds = datetime.now(timezone.utc).timestamp() - os.path.getmtime(SP500_CACHE_PATH)
    return age_seconds < SP500_CACHE_TTL_DAYS * 86400


def _fetch_sp500_from_wikipedia() -> set:
    try:
        resp = requests.get(WIKIPEDIA_SP500_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", {"id": "constituents"})
        if not table:
            logger.error("S&P 500 constituents table not found on Wikipedia")
            return set()
        tickers = set()
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            raw = cells[0].get_text(strip=True)
            # Wikipedia uses BRK.B form already; Alpaca also uses BRK.B
            tickers.add(raw)
        logger.info(f"Fetched {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500 list from Wikipedia: {e}")
        return set()


def fetch_insider_purchases(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list:
    """
    Fetch recent Form 4 open-market purchases from OpenInsider.
    Returns the raw parsed rows (before S&P 500 / value filtering).
    """
    params = {
        "xp": 1,          # transaction type: purchases (code P)
        "fd": lookback_days,  # filed within last N days
        "cnt": 200,       # pull up to 200 rows
        "sortcol": 0,     # sort by filing date desc
    }
    try:
        resp = requests.get(
            OPENINSIDER_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"OpenInsider fetch failed: {e}")
        return []

    return _parse_openinsider_table(resp.text)


def _parse_openinsider_table(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="tinytable")
    if not table:
        logger.error("OpenInsider tinytable not found in response")
        return []

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 13:
            continue

        try:
            filing_datetime = cells[1].get_text(strip=True)
            trade_date = cells[2].get_text(strip=True)
            ticker = cells[3].get_text(strip=True)
            company = cells[4].get_text(strip=True)
            insider = cells[5].get_text(strip=True)
            title = cells[6].get_text(strip=True)
            trade_type = cells[7].get_text(strip=True)
            price = _parse_money(cells[8].get_text(strip=True))
            qty = _parse_int(cells[9].get_text(strip=True))
            owned_after = _parse_int(cells[10].get_text(strip=True))
            delta_own = cells[11].get_text(strip=True)
            value = _parse_money(cells[12].get_text(strip=True))
        except Exception as e:
            logger.debug(f"Row parse error (skipping): {e}")
            continue

        rows.append({
            "filing_datetime": filing_datetime,
            "trade_date": trade_date,
            "ticker": ticker,
            "company": company,
            "insider": insider,
            "title": title,
            "trade_type": trade_type,
            "price": price,
            "shares": qty,
            "owned_after": owned_after,
            "delta_ownership": delta_own,
            "value": value,
        })

    return rows


def _parse_money(text: str) -> float:
    if not text:
        return 0.0
    cleaned = re.sub(r"[^0-9\-.]", "", text)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _parse_int(text: str) -> int:
    if not text:
        return 0
    cleaned = re.sub(r"[^0-9\-]", "", text)
    try:
        return int(cleaned) if cleaned else 0
    except ValueError:
        return 0


def get_qualifying_form4_buys(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_value: float = MIN_PURCHASE_VALUE,
    sp500_only: bool = True,
) -> list:
    """
    Main entry point: returns the list of Form 4 buys that meet ALL filters:
    - transaction type starts with "P" (open-market purchase)
    - value >= min_value
    - ticker is in current S&P 500 (when sp500_only=True)

    Each entry: {ticker, company, insider, title, trade_date, filing_datetime,
                 shares, price, value, owned_after, delta_ownership}
    """
    sp500 = get_sp500_tickers() if sp500_only else None
    if sp500_only and not sp500:
        logger.warning("S&P 500 list unavailable; returning empty (fail safe)")
        return []

    all_rows = fetch_insider_purchases(lookback_days=lookback_days)
    qualifying = []
    for row in all_rows:
        if not row["trade_type"].upper().startswith("P"):
            continue
        if row["value"] < min_value:
            continue
        if sp500_only and row["ticker"] not in sp500:
            continue
        qualifying.append(row)

    logger.info(
        f"Form 4 filter: {len(all_rows)} raw rows → {len(qualifying)} qualifying buys "
        f"(min ${min_value:,.0f}, {'S&P 500 only' if sp500_only else 'all'})"
    )
    return qualifying


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    buys = get_qualifying_form4_buys()
    print(f"\nQualifying buys: {len(buys)}\n")
    for b in buys:
        print(
            f"{b['ticker']:6s} {b['company'][:40]:40s} | "
            f"{b['insider'][:25]:25s} ({b['title'][:20]:20s}) | "
            f"{b['shares']:>8,} @ ${b['price']:>7,.2f} = ${b['value']:>12,.0f} | "
            f"filed {b['filing_datetime']}"
        )
