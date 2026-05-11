"""
BZP Scraper v3 — uses mo-board/api/v1/Board/Search (GET, returns JSON).
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

# ---------- Config ----------

BZP_SEARCH_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/Board/Search"
BZP_NOTICE_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/Board/GetNoticePdfById"
PIPELINE_URL = os.getenv("PIPELINE_URL", "http://localhost:8000")

# CPV prefixes relevant to Semicon
SEMICON_CPV_PREFIXES = [
    "316",   # Wiązki przewodów, kable
    "317",   # Elementy elektroniczne
    "320",   # Sprzęt telekomunikacyjny
    "321",   # Aparatura przesyłowa
    "324",   # Sprzęt multimedialny
    "325",   # Sprzęt sygnalizacyjny
    "326",   # Elementy sieci telekomunikacyjnej
    "334",   # Układy scalone, mikroprocesory
    "381",   # Przyrządy optyczne, lasery
    "503",   # Usługi naprawcze elektronika
    "713",   # Usługi inżynieryjne
]

# Keywords in orderObject to match even if CPV misses
SEMICON_KEYWORDS = [
    "pcb", "pcba", "smt", "tht", "montaż elektronik",
    "wiązk", "kablo", "laser", "diod",
    "komponent elektroniczn", "optoelektron",
    "płytk", "reballing", "bga", "szablon",
]

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


# ---------- BZP API ----------

def fetch_notices(date_from, date_to=None):
    """GET from BZP Board/Search — returns list of notice dicts."""
    params = {"DateFrom": date_from}
    if date_to:
        params["DateTo"] = date_to

    all_notices = []
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(BZP_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                all_notices = data
            elif isinstance(data, dict):
                all_notices = data.get("content", data.get("results", [data]))
    except Exception as e:
        print(f"[BZP API] Error: {e}")
    return all_notices


def matches_semicon(notice):
    """Check if notice matches Semicon profile by CPV or keywords."""
    cpv = (notice.get("cpvCode") or "").lower()
    subject = (notice.get("orderObject") or "").lower()
    org = (notice.get("organizationName") or "").lower()

    # Check CPV prefix
    for prefix in SEMICON_CPV_PREFIXES:
        if prefix.lower() in cpv.replace("-", "").replace(" ", ""):
            return True, f"CPV match: {prefix}"

    # Check keywords in subject
    for kw in SEMICON_KEYWORDS:
        if kw in subject:
            return True, f"Keyword match: {kw}"

    return False, ""


def fetch_notice_text(notice_id):
    """Fetch full notice text by ID."""
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(BZP_NOTICE_URL, params={"noticeId": notice_id})
            resp.raise_for_status()
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
    except Exception as e:
        print(f"  [Notice] Error: {e}")
        return ""


def build_tender_text(notice):
    """Build analysis text from notice JSON fields (fast, no extra API call)."""
    parts = []
    if notice.get("orderObject"):
        parts.append(f"Przedmiot: {notice['orderObject']}")
    if notice.get("cpvCode"):
        parts.append(f"CPV: {notice['cpvCode']}")
    if notice.get("organizationName"):
        parts.append(f"Zamawiający: {notice['organizationName']}")
    if notice.get("organizationCity"):
        parts.append(f"Miasto: {notice['organizationCity']}")
    if notice.get("organizationProvince"):
        parts.append(f"Województwo: {notice['organizationProvince']}")
    if notice.get("submittingOffersDate"):
        parts.append(f"Termin składania ofert: {notice['submittingOffersDate']}")
    if notice.get("orderType"):
        parts.append(f"Rodzaj: {notice['orderType']}")
    return "\n".join(parts)


# ---------- Pipeline ----------

def analyze_tender(tender_text):
    if len(tender_text) < 50:
        return None
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{PIPELINE_URL}/analyze",
                json={"tender_text": tender_text[:15000]},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"  [Pipeline] Error: {e}")
        return None


# ---------- Main ----------

def run_scan(days_back=1, min_score=20):
    print(f"\n{'='*60}")
    print(f"[{datetime.now().isoformat()}] BZP Scan Start")
    print(f"Range: {days_back} days | Min score: {min_score}")
    print(f"Pipeline: {PIPELINE_URL}")
    print(f"{'='*60}\n")

    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Step 1: Fetch all notices
    print(f"[1/3] Fetching notices from BZP (from {date_from})...")
    notices = fetch_notices(date_from)
    print(f"  -> Got {len(notices)} total notices\n")

    if not notices:
        print("[!] No notices returned from BZP API")
        return []

    # Step 2: Filter by CPV / keywords
    print(f"[2/3] Filtering by Semicon profile...")
    matched = []
    for n in notices:
        is_match, reason = matches_semicon(n)
        if is_match:
            matched.append((n, reason))

    print(f"  -> {len(matched)} matches out of {len(notices)}\n")

    # Step 3: Analyze matched notices
    print(f"[3/3] Analyzing {len(matched)} notices with AI pipeline...\n")
    scored = []

    for i, (notice, match_reason) in enumerate(matched):
        title = (notice.get("orderObject") or "?")[:80]
        notice_id = notice.get("moIdentifier", notice.get("id", ""))
        bzp_num = notice.get("noticeNumber", "")
        print(f"  [{i+1}/{len(matched)}] {bzp_num}: {title}...")
        print(f"    Match reason: {match_reason}")

        # Try quick analysis from JSON fields first
        tender_text = build_tender_text(notice)

        # If too short, fetch full text
        if len(tender_text) < 200 and notice_id:
            full = fetch_notice_text(notice_id)
            if full:
                tender_text = full

        result = analyze_tender(tender_text)
        if not result:
            print("    -> Analysis failed")
            continue

        sc = result.get("scoring", {})
        score = sc.get("match_score", 0)
        print(f"    -> Score: {score}/100 | {sc.get('reasoning', '')[:80]}")

        if score >= min_score:
            scored.append({
                "notice_id": notice_id,
                "bzp_number": bzp_num,
                "title": notice.get("orderObject", ""),
                "organization": notice.get("organizationName", ""),
                "city": notice.get("organizationCity", ""),
                "cpv": notice.get("cpvCode", ""),
                "deadline": notice.get("submittingOffersDate", ""),
                "match_reason": match_reason,
                "score": score,
                "is_relevant": sc.get("is_relevant", False),
                "reasoning": sc.get("reasoning", ""),
                "key_requirements": sc.get("key_requirements", []),
                "strategic_advantage": sc.get("strategic_advantage", ""),
                "risk_factors": sc.get("risk_factors", []),
                "extracted": result.get("extracted", {}),
                "scanned_at": datetime.now().isoformat(),
                "bzp_url": f"{BZP_NOTICE_URL}?noticeId={notice_id}",
            })

        time.sleep(1)  # Throttle Claude API

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"scan_{ts}.json"

    data = {
        "scan_date": datetime.now().isoformat(),
        "days_back": days_back,
        "total_notices": len(notices),
        "cpv_keyword_matches": len(matched),
        "relevant_count": len(scored),
        "results": sorted(scored, key=lambda x: x["score"], reverse=True),
    }

    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, ensure_ascii=False, indent=2, fp=f)

    print(f"\n{'='*60}")
    print(f"DONE:")
    print(f"  Total from BZP:    {len(notices)}")
    print(f"  CPV/keyword match: {len(matched)}")
    print(f"  Relevant (>={min_score}):  {len(scored)}")
    if scored:
        print(f"  Best score:        {scored[0]['score']}")
    print(f"  Saved: {out}")
    print(f"{'='*60}\n")

    return scored


if __name__ == "__main__":
    run_scan(days_back=7, min_score=20)
