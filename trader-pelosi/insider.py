#!/usr/bin/env python3
"""SEBI insider trading (PIT) and bulk/block deal tracker for trader-insider.
Standard library only. Zero third-party dependencies.

Tracks disclosures under:
  1. SEBI (Prohibition of Insider Trading) Regulations 2015 - Regulation 7(2):
     Disclosures by Promoters, Directors, Key Managerial Personnel (KMPs),
     and Designated Persons regarding acquisition or disposal of shares.
  2. NSE / BSE Bulk and Block Deals:
     Large institutional / HNI transactions where single transactions exceed
     0.5% of total shares (Bulk) or >= Rs 10 Crore in a single block window (Block).

Commands:
    python3 insider.py pit --symbol RELIANCE.NS            # PIT disclosures for a ticker
    python3 insider.py pit --promoter-only                # promoter buys/sells across market
    python3 insider.py deals --symbol TATASTEEL.NS         # bulk & block deals
    python3 insider.py new                                 # only disclosures since last check
    python3 insider.py pit --since 2026-10-01 --min-val 10000000 # trades >= Rs 1 Crore

State is kept in trader/state/insider.json so `new` rings each trade once.
Offline: --offline FILE reads saved disclosures JSON without network calls.
"""

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

NSE_PIT_URL = "https://www.nseindia.com/api/corporates-pit?index=equities"
NSE_BULK_URL = "https://www.nseindia.com/api/historical/bulk-deals"
NSE_BLOCK_URL = "https://www.nseindia.com/api/historical/block-deals"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


class InsiderError(Exception):
    pass


def _money_inr(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f >= 10000000:
        return "₹%.2f Cr" % (f / 10000000.0)
    elif f >= 100000:
        return "₹%.2f L" % (f / 100000.0)
    s = "{:,.2f}".format(f)
    return "₹" + (s[:-3] if s.endswith(".00") else s)


def clean_symbol(sym):
    s = str(sym or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s.rsplit(".", 1)[0]
    return s


def hash_record(rec):
    """Stable fingerprint for deduplication."""
    keys = sorted(rec.keys())
    blob = "|".join("%s:%s" % (k, rec[k]) for k in keys if k not in ("seen_at",))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise InsiderError("HTTP %d accessing %s" % (e.code, url))
    except urllib.error.URLError as e:
        raise InsiderError("could not reach %s: %s" % (url, e.reason))
    except json.JSONDecodeError as e:
        raise InsiderError("invalid JSON from %s: %s" % (url, e))


def parse_pit_data(raw_data):
    """Normalize raw SEBI PIT JSON payload into structured trade rows."""
    items = raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data
    if not isinstance(items, list):
        return []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sym = clean_symbol(it.get("symbol") or it.get("secSymbol") or "")
        person = str(it.get("acqName") or it.get("personName") or it.get("name") or "Unknown").strip()
        cat = str(it.get("personCategory") or it.get("category") or "Promoter/Director").strip()
        txn = str(it.get("tdpTransactionType") or it.get("acqMode") or it.get("type") or "Buy").strip()
        
        # Quantity and value
        qty = 0
        try:
            qty = int(float(it.get("secAcq") or it.get("quantity") or 0))
        except (ValueError, TypeError):
            pass
        
        val = 0.0
        try:
            val = float(it.get("valAcq") or it.get("value") or it.get("valueOfSecurities") or 0.0)
        except (ValueError, TypeError):
            pass

        date = str(it.get("date") or it.get("dateOfAcqFrom") or it.get("intimationDate") or "")[:10]
        mode = str(it.get("acqMode") or it.get("mode") or "Market Purchase").strip()

        is_buy = any(b in txn.lower() for b in ("buy", "acquisition", "purchase", "allotment"))
        side = "BUY" if is_buy else "SELL"

        row = {
            "symbol": sym,
            "person": person,
            "category": cat,
            "side": side,
            "quantity": qty,
            "value": val,
            "value_formatted": _money_inr(val),
            "date": date,
            "mode": mode,
            "raw_txn": txn,
        }
        row["fingerprint"] = hash_record(row)
        rows.append(row)
    return rows


def parse_deals_data(raw_data):
    """Normalize raw Bulk/Block deal JSON payload into structured rows."""
    items = raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data
    if not isinstance(items, list):
        return []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sym = clean_symbol(it.get("symbol") or "")
        client = str(it.get("clientName") or it.get("client") or "").strip()
        deal_type = str(it.get("dealType") or it.get("type") or "BULK").upper()
        side = str(it.get("buySell") or it.get("side") or "BUY").upper()
        
        qty = 0
        try:
            qty = int(float(it.get("quantityTraded") or it.get("qty") or 0))
        except (ValueError, TypeError):
            pass
        
        price = 0.0
        try:
            price = float(it.get("tradePrice") or it.get("price") or 0.0)
        except (ValueError, TypeError):
            pass

        val = qty * price
        date = str(it.get("date") or it.get("tradeDate") or "")[:10]

        row = {
            "symbol": sym,
            "client": client,
            "deal_type": deal_type,
            "side": "BUY" if "BUY" in side else "SELL",
            "quantity": qty,
            "price": price,
            "value": val,
            "value_formatted": _money_inr(val),
            "date": date,
        }
        row["fingerprint"] = hash_record(row)
        rows.append(row)
    return rows


def load_state(path="trader/state/insider.json"):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (ValueError, OSError):
            pass
    return {"seen_fingerprints": [], "last_check": None}


def save_state(path, state):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def filter_rows(rows, symbol=None, side=None, since=None, min_val=None, promoter_only=False):
    out = []
    sym_clean = clean_symbol(symbol) if symbol else None
    for r in rows:
        if sym_clean and r["symbol"] != sym_clean:
            continue
        if side and r["side"].upper() != side.upper():
            continue
        if since and r.get("date") and r["date"] < since:
            continue
        if min_val and float(r.get("value") or 0) < float(min_val):
            continue
        if promoter_only:
            cat = r.get("category", "").lower()
            if not any(k in cat for k in ("promoter", "director", "kmp")):
                continue
        out.append(r)
    return out


def render_pit_table(rows):
    if not rows:
        return "No SEBI PIT disclosures found matching criteria."
    lines = [
        "SEBI Prohibition of Insider Trading (PIT) Disclosures:",
        "%-12s %-6s %-12s %-30s %-18s %s" % ("SYMBOL", "SIDE", "VALUE", "INSIDER / ENTITY", "CATEGORY", "DATE"),
        "-" * 95
    ]
    for r in rows:
        lines.append("%-12s %-6s %-12s %-30.30s %-18.18s %s" % (
            r["symbol"], r["side"], r["value_formatted"], r["person"], r["category"], r.get("date", "")
        ))
    return "\n".join(lines)


def render_deals_table(rows):
    if not rows:
        return "No Bulk / Block deals found matching criteria."
    lines = [
        "NSE / BSE Bulk and Block Deals:",
        "%-12s %-6s %-6s %-12s %-8s %-32s %s" % ("SYMBOL", "TYPE", "SIDE", "VALUE", "PRICE", "CLIENT NAME", "DATE"),
        "-" * 95
    ]
    for r in rows:
        lines.append("%-12s %-6s %-6s %-12s %-8.2f %-32.32s %s" % (
            r["symbol"], r.get("deal_type", "BULK"), r["side"], r["value_formatted"],
            r.get("price", 0.0), r["client"], r.get("date", "")
        ))
    return "\n".join(lines)


def cmd_pit(a):
    if a.offline:
        with open(a.offline, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = fetch_url(NSE_PIT_URL)
    
    rows = parse_pit_data(data)
    filtered = filter_rows(rows, symbol=a.symbol, side=a.side, since=a.since,
                           min_val=a.min_val, promoter_only=a.promoter_only)
    if a.json:
        print(json.dumps(filtered, indent=2))
    else:
        print(render_pit_table(filtered))
        if filtered:
            print("\nTotal disclosures: %d" % len(filtered))
    return 0 if filtered else 1


def cmd_deals(a):
    url = NSE_BLOCK_URL if (a.type and a.type.lower() == "block") else NSE_BULK_URL
    if a.offline:
        with open(a.offline, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = fetch_url(url)
    
    rows = parse_deals_data(data)
    filtered = filter_rows(rows, symbol=a.symbol, side=a.side, since=a.since, min_val=a.min_val)
    if a.json:
        print(json.dumps(filtered, indent=2))
    else:
        print(render_deals_table(filtered))
        if filtered:
            print("\nTotal deals: %d" % len(filtered))
    return 0 if filtered else 1


def cmd_new(a):
    state = load_state(a.state)
    seen = set(state.get("seen_fingerprints", []))
    
    if a.offline:
        with open(a.offline, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = fetch_url(NSE_PIT_URL)
    
    rows = parse_pit_data(data)
    filtered = filter_rows(rows, symbol=a.symbol)
    new_rows = [r for r in filtered if r["fingerprint"] not in seen]
    
    for r in new_rows:
        seen.add(r["fingerprint"])
    
    state["seen_fingerprints"] = list(seen)
    state["last_check"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_state(a.state, state)
    
    if a.json:
        print(json.dumps(new_rows, indent=2))
    else:
        if new_rows:
            print("NEW INSIDER DISCLOSURES (%d new):" % len(new_rows))
            print(render_pit_table(new_rows))
        else:
            print("No new insider disclosures since last check.")
    return 0 if new_rows else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="SEBI PIT insider disclosures and bulk/block deals.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--symbol", help="filter by ticker, e.g. RELIANCE.NS or RELIANCE")
        p.add_argument("--side", choices=["BUY", "SELL"], help="filter BUY or SELL")
        p.add_argument("--since", help="filter date >= YYYY-MM-DD")
        p.add_argument("--min-val", type=float, help="minimum transaction value in INR")
        p.add_argument("--json", action="store_true", help="output structured JSON")
        p.add_argument("--offline", metavar="FILE", help="path to saved JSON disclosures file")

    p = sub.add_parser("pit", help="SEBI PIT Regulation 7(2) insider trades")
    common(p)
    p.add_argument("--promoter-only", action="store_true", help="only Promoters/Directors/KMPs")

    p = sub.add_parser("deals", help="NSE / BSE bulk and block deals")
    common(p)
    p.add_argument("--type", choices=["bulk", "block"], default="bulk", help="bulk or block deal")

    p = sub.add_parser("new", help="only newly reported disclosures since last check")
    p.add_argument("--symbol", help="filter by ticker")
    p.add_argument("--state", default="trader/state/insider.json")
    p.add_argument("--offline", metavar="FILE")
    p.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"pit": cmd_pit, "deals": cmd_deals, "new": cmd_new}[a.cmd](a)
    except InsiderError as e:
        print("insider.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
