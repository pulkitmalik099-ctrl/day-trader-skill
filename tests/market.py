"""
trader-common: Shared market definitions and helpers for US (NYSE/NASDAQ) and Indian (NSE/BSE) markets.
Pure standard-library Python without external dependencies.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
from typing import Optional, Tuple, Dict, Any, List

# Timezones
# US uses America/New_York (Eastern), which observes Daylight Saving Time.
# India uses Asia/Kolkata (IST = UTC+5:30) with NO Daylight Saving Time.
IST_OFFSET = _dt.timedelta(hours=5, minutes=30)
EPOCH = _dt.datetime(1970, 1, 1)

# Trading Hours
US_OPEN = _dt.time(9, 30)
US_CLOSE = _dt.time(16, 0)
US_EARLY_CLOSE = _dt.time(13, 0)

INDIA_OPEN = _dt.time(9, 15)
INDIA_CLOSE = _dt.time(15, 30)
INDIA_PREMARKET_OPEN = _dt.time(9, 0)
INDIA_PREMARKET_CLOSE = _dt.time(9, 15)

MARKET_HOURS = {
    "US": (US_OPEN, US_CLOSE),
    "IN": (INDIA_OPEN, INDIA_CLOSE),
}

# Holidays - US (NYSE)
NYSE_HOLIDAYS: Dict[str, str] = {
    "2026-01-01": "New Year's Day",
    "2026-01-19": "Martin Luther King Jr. Day",
    "2026-02-16": "Washington's Birthday",
    "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observed)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving Day",
    "2026-12-25": "Christmas Day",
    "2027-01-01": "New Year's Day",
    "2027-01-18": "Martin Luther King Jr. Day",
    "2027-02-15": "Washington's Birthday",
    "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day",
    "2027-06-18": "Juneteenth (observed)",
    "2027-07-05": "Independence Day (observed)",
    "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving Day",
    "2027-12-24": "Christmas Day (observed)",
}

NYSE_EARLY_CLOSE: Dict[str, str] = {
    "2026-07-02": "Day before Independence Day",
    "2026-11-27": "Day after Thanksgiving (Black Friday)",
    "2026-12-24": "Christmas Eve",
    "2027-11-26": "Day after Thanksgiving (Black Friday)",
}

# Holidays - India (NSE/BSE) 2026-2027
NSE_HOLIDAYS: Dict[str, str] = {
    "2026-01-26": "Republic Day",
    "2026-03-10": "Maha Shivaratri",
    "2026-03-17": "Holi",
    "2026-03-31": "Id-Ul-Fitr (Ramadan Eid)",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-06-07": "Bakri Id / Id-Ul-Adha",
    "2026-07-06": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-08-19": "Janmashtami",
    "2026-09-05": "Milad-Un-Nabi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Diwali Laxmi Pujan",
    "2026-10-21": "Diwali Balipratipada",
    "2026-11-05": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas",
    "2027-01-26": "Republic Day",
    "2027-02-27": "Maha Shivaratri",
    "2027-03-08": "Holi",
    "2027-03-22": "Id-Ul-Fitr",
    "2027-03-26": "Good Friday",
    "2027-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2027-05-01": "Maharashtra Day",
    "2027-05-28": "Bakri Id / Id-Ul-Adha",
    "2027-06-25": "Muharram",
    "2027-08-09": "Janmashtami",
    "2027-08-15": "Independence Day",
    "2027-08-25": "Milad-Un-Nabi",
    "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-11-08": "Diwali Laxmi Pujan",
    "2027-11-09": "Diwali Balipratipada",
    "2027-11-25": "Guru Nanak Jayanti",
    "2027-12-25": "Christmas",
}

# URLs & Universe files
NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY_500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements?index=equities"
NSE_PIT_URL = "https://www.nseindia.com/api/corporates-pit?index=equities"

DEFAULT_UNIVERSE_US = "trader/universe.txt"
DEFAULT_UNIVERSE_IN = "trader/universe_in.txt"


def eastern_offset(utc_dt: _dt.datetime) -> _dt.timedelta:
    """Return UTC offset for US Eastern time (EDT = -4, EST = -5)."""
    naive = utc_dt.replace(tzinfo=None) if utc_dt.tzinfo is not None else utc_dt
    year = naive.year
    mar = _dt.datetime(year, 3, 1)
    dls_start = _dt.datetime(year, 3, 8 + (6 - mar.weekday()) % 7, 7, 0)
    nov = _dt.datetime(year, 11, 1)
    dls_end = _dt.datetime(year, 11, 1 + (6 - nov.weekday()) % 7, 6, 0)
    return _dt.timedelta(hours=-4 if dls_start <= naive < dls_end else -5)


def to_eastern(utc: _dt.datetime) -> _dt.datetime:
    """Aware or naive UTC -> naive Eastern (ET)."""
    if utc.tzinfo is not None:
        utc = utc.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return utc + eastern_offset(utc)


def eastern_to_utc(local: _dt.datetime) -> _dt.datetime:
    """Naive Eastern -> naive UTC."""
    approx = local + _dt.timedelta(hours=5)
    return local - eastern_offset(approx)


def to_ist(utc: _dt.datetime) -> _dt.datetime:
    """Aware or naive UTC -> naive Indian Standard Time (IST = UTC+5:30, no DST)."""
    if utc.tzinfo is not None:
        utc = utc.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return utc + IST_OFFSET


def ist_to_utc(local: _dt.datetime) -> _dt.datetime:
    """Naive IST -> naive UTC."""
    return local - IST_OFFSET


def to_market_tz(utc: _dt.datetime, market: str = "US") -> _dt.datetime:
    """Convert UTC datetime to naive local datetime for the given market."""
    m = market.upper()
    if m in ("IN", "INDIA", "NSE", "BSE"):
        return to_ist(utc)
    return to_eastern(utc)


def market_to_utc(local: _dt.datetime, market: str = "US") -> _dt.datetime:
    """Convert naive local market datetime to naive UTC."""
    m = market.upper()
    if m in ("IN", "INDIA", "NSE", "BSE"):
        return ist_to_utc(local)
    return eastern_to_utc(local)


def ts_to_market_tz(ts: int | float, market: str = "US") -> _dt.datetime:
    """Convert unix epoch timestamp to naive local market datetime."""
    utc = EPOCH + _dt.timedelta(seconds=int(ts))
    return to_market_tz(utc, market)


def tz_name(market: str = "US") -> str:
    """Return timezone string identifier (ET or IST)."""
    return "IST" if market.upper() in ("IN", "INDIA", "NSE", "BSE") else "ET"


def is_trading_day(d: _dt.date, market: str = "US") -> Tuple[bool, str]:
    """Check if date is an open trading day."""
    if d.weekday() >= 5:
        return False, "weekend"
    iso = d.isoformat()
    m = market.upper()
    if m in ("IN", "INDIA", "NSE", "BSE"):
        if iso in NSE_HOLIDAYS:
            return False, f"NSE holiday: {NSE_HOLIDAYS[iso]}"
        return True, ""
    else:
        if iso in NYSE_HOLIDAYS:
            return False, f"NYSE holiday: {NYSE_HOLIDAYS[iso]}"
        return True, ""


def session(d: _dt.date, market: str = "US") -> Optional[Tuple[_dt.time, _dt.time]]:
    """Return (open_time, close_time) for date, or None if closed."""
    ok, _ = is_trading_day(d, market)
    if not ok:
        return None
    m = market.upper()
    if m in ("IN", "INDIA", "NSE", "BSE"):
        return INDIA_OPEN, INDIA_CLOSE
    iso = d.isoformat()
    close = US_EARLY_CLOSE if iso in NYSE_EARLY_CLOSE else US_CLOSE
    return US_OPEN, close


def to_yahoo(symbol: str, market: str = "US") -> str:
    """Convert symbol to Yahoo Finance query symbol."""
    sym = symbol.upper().strip()
    m = market.upper()
    if m in ("IN", "INDIA", "NSE", "BSE"):
        if sym.endswith((".NS", ".BO")):
            return sym
        if m == "BSE":
            return f"{sym}.BO"
        return f"{sym}.NS"  # Default to NSE
    return sym.replace(".", "-")


def from_yahoo(yahoo_symbol: str, market: str = "US") -> str:
    """Strip exchange suffix or normalize back to base symbol."""
    sym = yahoo_symbol.upper().strip()
    m = market.upper()
    if m in ("IN", "INDIA", "NSE", "BSE"):
        for suffix in (".NS", ".BO"):
            if sym.endswith(suffix):
                return sym[:-len(suffix)]
        return sym
    return sym.replace("-", ".")


def currency_symbol(market: str = "US") -> str:
    """Return currency symbol ($ or ₹)."""
    return "₹" if market.upper() in ("IN", "INDIA", "NSE", "BSE") else "$"


def format_money(amount: float, market: str = "US") -> str:
    """Format money string with appropriate currency symbol."""
    sym = currency_symbol(market)
    return f"{sym}{amount:,.2f}"


def get_market(config_path: str = "trader/config.json") -> str:
    """Read configured market ('US' or 'IN') from config file if available."""
    if _os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
                val = data.get("market")
                if val:
                    return str(val).upper()
        except Exception:
            pass
    return "US"


def default_universe_path(market: str = "US") -> str:
    """Return default universe path for the given market."""
    return DEFAULT_UNIVERSE_IN if market.upper() in ("IN", "INDIA", "NSE", "BSE") else DEFAULT_UNIVERSE_US
