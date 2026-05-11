"""
BZP Scraper v2 — uses correct GET endpoints.

Sources:
1. searchbzp.uzp.gov.pl — public BZP search (GET, no auth)
2. mo-board API — fetch full notice text by ID
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

# ---------- Config ----------

SEARCH_BZP_URL = "https://searchbzp.uzp.gov.pl/Search/Results"
BZP_NOTICE_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/Board/GetNoticePdfById"
PIPELINE_URL = os.getenv("PIPELINE_URL", "http://localhost:8000")

SEMICON_SEARCH_QUERIES = [
    "montaż płytek PCB",
    "komponenty elektroniczne",
    "wiązki kablowe",
    "diody laserowe",
    "montaż kontraktowy elektronika",
    "SMT THT",
    "PCBA",
    "optoelektronika",
    "elementy elektroniczne",
    "szablony lutownicze",
]

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


# ---------- BZP Search ----------

def search_bzp(query, date_from=None, date_to=None, page=1):
    if not date_from:
        date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")

    params = {
        "SearchPhrase": query,
        "DateFrom": date_from,
        "DateTo": date_to,
        "Page": page,
        "SortingColumnName": "PublicationDate",
        "SortingDirection": "DESC",
        "Type": "Zamowienie",
    }

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(SEARCH_BZP_URL, params=params)
            resp.raise_for_status()
            return parse_search_html(resp.text, query)
    except Exception as e:
        print(f"  [BZP] Error for '{query}': {e}")
        return []


def parse_search_html(html, query):
    results = []
    seen = set()

    # Extract notice IDs from links
    ids = re.findall(r'noticeId=([a-f0-9\-]{30,})', html, re.IGNORECASE)
    for nid in ids:
        if nid not in seen:
            seen.add(nid)
            results.append({"noticeId": nid, "query": query})

    return results


def fetch_notice_text(notice_id):
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(BZP_NOTICE_URL, params={"noticeId": notice_id})
            resp.raise_for_status()
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
    except Exception as e:
        print(f"  [Notice] Error {notice_id}: {e}")
        return ""


# ---------- Pipeline ----------

def analyze_tender(tender_text):
    if len(tender_text) < 100:
        return None
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{PIPELINE_URL}/analyze",
                json={"tender_text": tender_text[:15000]},
                headers={"Content-Type": "application/json"},
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
    print(f"{'='*60}\n")

    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")

    all_notices = {}

    for query in SEMICON_SEARCH_QUERIES:
        print(f"[Search] '{query}'...")
        results = search_bzp(query, date_from=date_from, date_to=date_to)
        for r in results:
            nid = r["noticeId"]
            if nid not in all_notices:
                all_notices[nid] = query
        if results:
            print(f"  -> Found {len(results)}")
        time.sleep(0.5)

    print(f"\n[Total] Unique notices: {len(all_notices)}\n")

    scored = []

    for i, (nid, query) in enumerate(all_notices.items()):
        print(f"[{i+1}/{len(all_notices)}] Fetching {nid[:20]}...")

        text = fetch_notice_text(nid)
        if len(text) < 100:
            print("  -> Too short, skip")
            continue

        print(f"  -> {len(text)} chars. Analyzing...")
        result = analyze_tender(text)
        if not result:
            continue

        sc = result.get("scoring", {})
        score = sc.get("match_score", 0)
        print(f"  -> Score: {score}/100 | {sc.get('reasoning', '')[:80]}")

        if score >= min_score:
            scored.append({
                "notice_id": nid,
                "matched_query": query,
                "score": score,
                "is_relevant": sc.get("is_relevant", False),
                "reasoning": sc.get("reasoning", ""),
                "key_requirements": sc.get("key_requirements", []),
                "strategic_advantage": sc.get("strategic_advantage", ""),
                "risk_factors": sc.get("risk_factors", []),
                "extracted": result.get("extracted", {}),
                "scanned_at": datetime.now().isoformat(),
                "bzp_url": f"{BZP_NOTICE_URL}?noticeId={nid}",
            })

        time.sleep(2)

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"scan_{ts}.json"

    data = {
        "scan_date": datetime.now().isoformat(),
        "days_back": days_back,
        "queries_used": len(SEMICON_SEARCH_QUERIES),
        "notices_found": len(all_notices),
        "relevant_count": len(scored),
        "results": sorted(scored, key=lambda x: x["score"], reverse=True),
    }

    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, ensure_ascii=False, indent=2, fp=f)

    print(f"\n{'='*60}")
    print(f"DONE: {len(all_notices)} found, {len(scored)} relevant (>={min_score})")
    print(f"Saved: {out}")
    print(f"{'='*60}\n")

    return scored


if __name__ == "__main__":
    run_scan(days_back=1, min_score=20)
