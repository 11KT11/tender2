"""
Scheduler — odpala skan BZP co godzinę.
Uruchamiany osobno: python scheduler.py
Albo jako część Railway (osobny worker).
"""

import os
import time
from datetime import datetime

from scraper import run_scan

SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))
DAYS_BACK = int(os.getenv("DAYS_BACK", "1"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "20"))


def main():
    print(f"Semicon BZP Scanner")
    print(f"Interwał: co {SCAN_INTERVAL_MINUTES} minut")
    print(f"Pipeline URL: {os.getenv('PIPELINE_URL', 'http://localhost:8000')}")
    print(f"Min score: {MIN_SCORE}")
    print()

    while True:
        try:
            results = run_scan(days_back=DAYS_BACK, min_score=MIN_SCORE)

            if results:
                print(f"\n[!] Znaleziono {len(results)} trafnych przetargów!")
                for r in results[:5]:
                    print(f"    [{r['score']}/100] {r['title'][:60]}")
        except Exception as e:
            print(f"[ERROR] {datetime.now().isoformat()}: {e}")

        print(f"\nNastępny skan za {SCAN_INTERVAL_MINUTES} minut...")
        time.sleep(SCAN_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
