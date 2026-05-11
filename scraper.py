"""
BZP Scraper — pobiera ogłoszenia z API Platformy e-Zamówienia
i przepuszcza je przez pipeline scoringowy Semicon.

Dwa źródła:
1. API BZP WebService (oficjalne, darmowe, bez rejestracji)
   http://ezamowienia.gov.pl/mo-board/api/v1/notice
2. Wyszukiwarka BZP (fallback)
   https://searchbzp.uzp.gov.pl/
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

# ---------- Konfiguracja ----------

BZP_API_BASE = "https://ezamowienia.gov.pl/mo-board/api/v1"
BZP_SEARCH_URL = "https://searchbzp.uzp.gov.pl/Search/Results"
PIPELINE_URL = os.getenv("PIPELINE_URL", "http://localhost:8000")

# Kody CPV bliskie profilowi Semicon
# 31 - Sprzęt elektryczny, aparatura, oświetlenie
# 32 - Sprzęt telekomunikacyjny, radiowy, telewizyjny
# 38 - Instrumenty laboratoryjne, optyczne, precyzyjne
# 50 - Usługi naprawcze i konserwacyjne
SEMICON_CPV_PREFIXES = [
    "3100",  # Silniki, generatory, transformatory, aparatura rozdzielcza
    "3120",  # Aparatura rozdzielcza i sterownicza
    "3150",  # Oświetlenie i lampy elektryczne (lasery)
    "3160",  # Wiązki przewodów (cable harness!)
    "3170",  # Elementy elektroniczne / komponenty
    "3200",  # Nadajniki radiowe, TV, telekomunikacja
    "3210",  # Aparatura telefoniczna / przesyłowa
    "3240",  # Kamery / sprzęt multimedialny
    "3242",  # Sprzęt radarowy
    "3250",  # Sprzęt sygnalizacyjny
    "3260",  # Elementy sieci telekomunikacyjnej
    "3342",  # Układy scalone, mikroprocesory
    "3800",  # Instrumenty laboratoryjne, optyczne
    "3812",  # Przyrządy optyczne (lasery, diody)
    "3813",  # Urządzenia laserowe
    "5031",  # Usługi naprawcze sprzętu elektronicznego
    "5033",  # Usługi konserwacji sprzętu IT
    "7131",  # Usługi inżynieryjne
]

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


# ---------- BZP API Client ----------

def fetch_notices_from_api(
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 0,
    size: int = 50,
) -> list[dict]:
    """
    Pobiera ogłoszenia z BZP API.
    
    API endpoint: /mo-board/api/v1/Board/Search
    Zwraca listę ogłoszeń z podstawowymi danymi.
    """
    if not date_from:
        date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z")
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%dT23:59:59.999Z")

    # BZP Search API - POST z parametrami wyszukiwania
    search_payload = {
        "datePublicationFrom": date_from,
        "datePublicationTo": date_to,
        "page": page,
        "size": size,
        "sortField": "datePublication",
        "sortOrder": "desc",
    }

    try:
        with httpx.Client(timeout=30) as client:
            # Próbujemy oficjalne API
            resp = client.post(
                f"{BZP_API_BASE}/Board/Search",
                json=search_payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content", data.get("results", []))
    except Exception as e:
        print(f"[BZP API] Błąd: {e}")
        return []


def fetch_notice_detail(notice_id: str) -> str:
    """Pobiera pełną treść ogłoszenia po ID."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{BZP_API_BASE}/Board/GetNoticePdfById",
                params={"noticeId": notice_id},
            )
            resp.raise_for_status()
            # API zwraca HTML/tekst ogłoszenia
            return resp.text
    except Exception as e:
        print(f"[BZP Detail] Błąd dla {notice_id}: {e}")
        return ""


# ---------- Filtrowanie CPV ----------

def matches_cpv(notice: dict) -> bool:
    """Sprawdza czy ogłoszenie pasuje do kodów CPV Semicon."""
    cpv_codes = []

    # BZP API zwraca CPV w różnych formatach
    for key in ["cpvCode", "cpv", "mainCpvCode", "cpvCodes"]:
        val = notice.get(key, "")
        if isinstance(val, str):
            cpv_codes.append(val)
        elif isinstance(val, list):
            cpv_codes.extend(val)

    # Sprawdzamy też zagnieżdżone obiekty
    items = notice.get("items", [])
    for item in items:
        if isinstance(item, dict):
            cpv = item.get("cpvCode", item.get("mainCpvCode", ""))
            if cpv:
                cpv_codes.append(cpv)

    # Czyścimy kody (usuwamy myślniki, spacje)
    clean_codes = [c.replace("-", "").replace(".", "").strip()[:4] for c in cpv_codes if c]

    # Sprawdzamy dopasowanie prefiksów
    for code in clean_codes:
        for prefix in SEMICON_CPV_PREFIXES:
            if code.startswith(prefix[:len(code)]) or prefix.startswith(code[:len(prefix)]):
                return True
    return False


def extract_text_from_notice(notice: dict) -> str:
    """
    Wyciąga tekst ogłoszenia z różnych pól API BZP.
    API zwraca dane w różnych strukturach - obsługujemy wszystkie.
    """
    text_parts = []

    # Bezpośrednie pola tekstowe
    text_fields = [
        "title", "objectDescription", "shortDescription",
        "description", "subject", "noticeTitle",
        "additionalInformation", "conditions",
    ]
    for field in text_fields:
        val = notice.get(field, "")
        if val:
            text_parts.append(f"{field}: {val}")

    # Zagnieżdżone opisy
    for section_key in ["sections", "sectionsList", "formData"]:
        sections = notice.get(section_key, [])
        if isinstance(sections, list):
            for section in sections:
                if isinstance(section, dict):
                    for k, v in section.items():
                        if isinstance(v, str) and len(v) > 20:
                            text_parts.append(v)

    # Jeśli za mało tekstu — pobierz pełne ogłoszenie
    combined = "\n".join(text_parts)
    if len(combined) < 200:
        notice_id = notice.get("id", notice.get("noticeId", ""))
        if notice_id:
            full_text = fetch_notice_detail(notice_id)
            if full_text:
                combined = full_text

    return combined


# ---------- Pipeline Integration ----------

def analyze_tender(tender_text: str) -> dict | None:
    """Wysyła tekst przetargu do pipeline'a scoringowego na Railway."""
    if len(tender_text) < 50:
        return None

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{PIPELINE_URL}/analyze",
                json={"tender_text": tender_text[:15000]},  # limit tokenów
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[Pipeline] Błąd analizy: {e}")
        return None


# ---------- Główny flow ----------

def run_scan(days_back: int = 1, min_score: int = 20):
    """
    Główna funkcja: skanuje BZP → filtruje CPV → analizuje → zapisuje wyniki.
    """
    print(f"\n{'='*60}")
    print(f"[{datetime.now().isoformat()}] Start skanowania BZP (ostatnie {days_back} dni)")
    print(f"{'='*60}\n")

    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00.000Z")

    all_results = []
    page = 0
    total_fetched = 0
    cpv_matched = 0

    while True:
        notices = fetch_notices_from_api(date_from=date_from, page=page)
        if not notices:
            break

        total_fetched += len(notices)
        print(f"[BZP] Pobrano stronę {page}: {len(notices)} ogłoszeń")

        for notice in notices:
            # Filtr CPV
            if not matches_cpv(notice):
                continue

            cpv_matched += 1
            title = notice.get("title", notice.get("noticeTitle", "brak tytułu"))
            notice_id = notice.get("id", notice.get("noticeId", "?"))
            print(f"\n  → CPV match: {title[:80]}...")

            # Wyciągnij tekst i przeanalizuj
            tender_text = extract_text_from_notice(notice)
            result = analyze_tender(tender_text)

            if result:
                score = result.get("scoring", {}).get("match_score", 0)
                relevant = result.get("scoring", {}).get("is_relevant", False)
                reasoning = result.get("scoring", {}).get("reasoning", "")

                print(f"    Score: {score}/100 | Relevant: {relevant}")
                print(f"    {reasoning}")

                if score >= min_score:
                    entry = {
                        "notice_id": notice_id,
                        "title": title,
                        "score": score,
                        "is_relevant": relevant,
                        "reasoning": reasoning,
                        "analysis": result,
                        "scanned_at": datetime.now().isoformat(),
                        "bzp_url": f"https://ezamowienia.gov.pl/mo-board/api/v1/Board/GetNoticePdfById?noticeId={notice_id}",
                    }
                    all_results.append(entry)

            # Throttle — nie bombarduj API
            time.sleep(1)

        page += 1
        if page > 20:  # Max 1000 ogłoszeń per scan
            break

    # Zapisz wyniki
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = RESULTS_DIR / f"scan_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scan_date": datetime.now().isoformat(),
                "total_fetched": total_fetched,
                "cpv_matched": cpv_matched,
                "analyzed_and_relevant": len(all_results),
                "results": sorted(all_results, key=lambda x: x["score"], reverse=True),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n{'='*60}")
    print(f"PODSUMOWANIE:")
    print(f"  Pobrano ogłoszeń:       {total_fetched}")
    print(f"  Pasujących CPV:         {cpv_matched}")
    print(f"  Trafnych (score>={min_score}): {len(all_results)}")
    print(f"  Zapisano do:            {output_file}")
    print(f"{'='*60}\n")

    return all_results


if __name__ == "__main__":
    run_scan(days_back=1, min_score=20)
