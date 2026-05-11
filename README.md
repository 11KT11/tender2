# Semicon Tender Analyzer

Dwuetapowy pipeline do automatycznej analizy przetargów pod kątem dopasowania do profilu Semicon Sp. z o.o.

## Jak działa

```
Surowy tekst przetargu
        ↓
  [Etap 1: Ekstrakcja]  →  ustrukturyzowane fakty (JSON)
        ↓
  [Etap 2: Scoring]     →  wynik dopasowania 0-100 + analiza
        ↓
  Kompletna odpowiedź JSON
```

## Szybki start (lokalnie)

```bash
# 1. Sklonuj repo
git clone <your-repo-url> && cd semicon-tender-analyzer

# 2. Ustaw klucz API
cp .env.example .env
# Edytuj .env i wklej swój ANTHROPIC_API_KEY

# 3. Zainstaluj i odpal
pip install -r requirements.txt
uvicorn main:app --reload
```

API dostępne pod `http://localhost:8000`

## Endpointy

| Metoda | Ścieżka    | Opis                                   |
|--------|------------|----------------------------------------|
| POST   | /analyze   | Pełny pipeline: ekstrakcja + scoring   |
| POST   | /extract   | Tylko Etap 1 (debug ekstrakcji)        |
| POST   | /score     | Tylko Etap 2 (podaj gotowe dane)       |
| GET    | /health    | Healthcheck                            |
| GET    | /docs      | Swagger UI (automatyczne)              |

## Przykład użycia

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "tender_text": "Przedmiotem zamówienia jest dostawa i montaż płytek PCB w technologii SMT dla Ministerstwa Obrony Narodowej. Wymagany certyfikat AS9100. Termin składania ofert: 2025-02-15. Wadium: 10 000 PLN. Realizacja: Warszawa."
  }'
```

## Deploy na Railway (najszybciej)

1. Push repo na GitHub
2. Wejdź na [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Dodaj zmienną środowiskową: `ANTHROPIC_API_KEY`
4. Railway automatycznie wykryje Dockerfile i zbuduje
5. Gotowe — dostajesz publiczny URL

## Deploy na Render

1. Push na GitHub
2. [render.com](https://render.com) → New Web Service → Connect repo
3. Settings: Runtime = Docker, dodaj env var `ANTHROPIC_API_KEY`
4. Deploy

## Koszt

~4-6 centów za analizę jednego przetargu (2 calle Claude Sonnet).
50 przetargów/dzień ≈ $2-3/dzień.
