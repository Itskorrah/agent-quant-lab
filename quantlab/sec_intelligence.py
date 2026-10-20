"""Opt-in SEC filing context for MNQ research; not a tradable timestamp signal.

Inspired by the public-filing monitor in trader-skill (MIT). This standalone
module neither sends alerts nor trades and does no networking unless called
explicitly with fetch=True.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

FORMS = frozenset({"8-K", "10-Q", "10-K"})
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,9}\Z")
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}\Z")
_MAX_BYTES = 3_000_000


def watchlist_entries(data: dict) -> list[dict]:
    if not isinstance(data, dict) or set(data) != {"watchlist"} or not isinstance(data["watchlist"], list):
        raise ValueError("Watchlist must contain a watchlist array")
    rows = data["watchlist"]
    if not 1 <= len(rows) <= 12:
        raise ValueError("Watchlist must contain 1–12 entries")
    cleaned, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"symbol", "cik"}:
            raise ValueError("Each watchlist entry requires symbol and cik only")
        sym, cik = row["symbol"], row["cik"]
        if not isinstance(sym, str) or not _SYMBOL.fullmatch(sym):
            raise ValueError("Invalid stock symbol")
        if not isinstance(cik, str) or not re.fullmatch(r"\d{1,10}", cik):
            raise ValueError("CIK must be a numeric string")
        cik = cik.zfill(10)
        if sym in seen or cik in {x["cik"] for x in cleaned}:
            raise ValueError("Duplicate symbol or CIK")
        seen.add(sym)
        cleaned.append({"symbol": sym, "cik": cik})
    return cleaned


def _utc_instant(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Observation time must be ISO-8601 UTC")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Observation time must be ISO-8601 UTC") from exc
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("Observation time must have explicit UTC timezone")
    return dt.astimezone(timezone.utc).isoformat()


def _date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Invalid SEC filing date")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("Invalid SEC filing date") from exc


def parse_submissions(payload: dict, entry: dict, *, since: str | None = None) -> list[dict]:
    """Normalise SEC submissions; never treat unzoned acceptance times as UTC."""
    if not isinstance(payload, dict) or not isinstance(payload.get("filings"), dict):
        raise ValueError("Not an SEC submissions response")
    cik = entry["cik"]
    if str(payload.get("cik", "")).zfill(10) != cik:
        raise ValueError("SEC CIK mismatch")
    recent = payload["filings"].get("recent")
    required = ("form", "accessionNumber", "filingDate")
    if not isinstance(recent, dict) or any(not isinstance(recent.get(k), list) for k in required):
        raise ValueError("Missing SEC recent filings arrays")
    n = len(recent["form"])
    if any(len(recent[k]) != n for k in required):
        raise ValueError("SEC recent filing arrays not aligned")
    accepts = recent.get("acceptanceDateTime")
    if accepts is not None and (not isinstance(accepts, list) or len(accepts) != n):
        raise ValueError("SEC acceptance timestamps not aligned")
    since = _date(since) if since is not None else None
    result, seen = [], set()
    for idx in range(n):
        form = recent["form"][idx]
        if form not in FORMS:
            continue
        accession = recent["accessionNumber"][idx]
        filing_date = _date(recent["filingDate"][idx])
        if not isinstance(accession, str) or not _ACCESSION.fullmatch(accession):
            raise ValueError("Malformed SEC accession number")
        if since is not None and filing_date < since:
            continue
        if accession in seen:
            continue
        seen.add(accession)
        accepted = accepts[idx] if accepts is not None else None
        if accepted is not None and (not isinstance(accepted, str) or
                                     not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", accepted)):
            raise ValueError("Malformed unzoned SEC acceptance timestamp")
        result.append({
            "symbol": entry["symbol"], "cik": cik, "form": form,
            "accession": accession, "filing_date": filing_date,
            "acceptance_time_unzoned": accepted,
            "filing_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/",
        })
    return sorted(result, key=lambda x: (x["filing_date"], x["symbol"], x["accession"]), reverse=True)


def fetch_submissions(cik: str, *, user_agent: str) -> bytes:
    if not isinstance(user_agent, str) or "@" not in user_agent or len(user_agent) > 200 or "\n" in user_agent or "\r" in user_agent:
        raise ValueError("SEC_USER_AGENT must identify a contact with an email")
    if not re.fullmatch(r"\d{10}", cik):
        raise ValueError("Invalid SEC CIK")
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        raw = response.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("SEC response exceeds size cap")
    return raw


def scan_watchlist(watchlist: dict, *, offline_dir: str | Path | None = None, fetch: bool = False,
                   observed_at_utc: str, since: str | None = None, user_agent: str | None = None) -> dict:
    if bool(offline_dir) == bool(fetch):
        raise ValueError("Choose exactly one of offline_dir and explicit fetch")
    observed = _utc_instant(observed_at_utc)
    rows = watchlist_entries(watchlist)
    events, sources = [], []
    for row in rows:
        url = f"https://data.sec.gov/submissions/CIK{row['cik']}.json"
        if fetch:
            raw = fetch_submissions(row["cik"], user_agent=user_agent or "")
        else:
            path = Path(offline_dir) / f"CIK{row['cik']}.json"
            if not path.is_file() or path.stat().st_size > _MAX_BYTES:
                raise ValueError("Offline SEC fixture missing or exceeds size cap")
            raw = path.read_bytes()
        if len(raw) > _MAX_BYTES:
            raise ValueError("SEC submission too large")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Malformed SEC submission JSON") from exc
        events.extend(parse_submissions(payload, row, since=since))
        sources.append({"symbol": row["symbol"], "cik": row["cik"], "api_url": url,
                        "content_sha256": hashlib.sha256(raw).hexdigest()})
    return {"schema_version": 1, "kind": "sec_filing_context_only", "source": "SEC EDGAR submissions",
            "observed_at_utc": observed, "observed_time_basis": "runtime_clock" if fetch else "user_declared",
            "watchlist": rows, "sources": sources,
            "filings": sorted(events, key=lambda x: (x["filing_date"], x["symbol"], x["accession"]), reverse=True),
            "filings_count": len(events), "eligible_for_signals": False,
            "eligible_for_paper": False, "eligible_for_live": False,
            "warnings": ["SEC filings are contextual only; not validated MNQ trading signals",
                         "Filing dates are day-level and acceptance timestamps have no explicit UTC offset",
                         "Offline observation time is user-declared, not proof of historical availability" if not fetch else
                         "Retrieval time documents observation, not necessarily first public availability"]}


def write_snapshot(path: str | Path, report: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    return path
