import json
import os
from datetime import date

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import AnalyzeRequest, AnalyzeResponse, ExtractedTender, ScoringResult
from prompts import EXTRACTION_PROMPT, SCORING_PROMPT

app = FastAPI(
    title="Semicon Tender Analyzer",
    description="Dwuetapowa analiza przetargów pod kątem dopasowania do profilu Semicon Sp. z o.o.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Claude API client ----------

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = os.getenv("MODEL", "claude-sonnet-4-20250514")
MAX_RETRIES = 2


def _call_claude(prompt: str) -> str:
    """Single Claude API call with basic retry."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise HTTPException(status_code=502, detail=f"Claude API error: {e}")
    return ""


def _parse_json(raw: str) -> dict:
    """Parse JSON from Claude response, stripping markdown fences if present."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Claude returned invalid JSON: {e}\n\nRaw output:\n{raw[:500]}",
        )


# ---------- Pipeline stages ----------

def stage_1_extract(tender_text: str) -> ExtractedTender:
    """Stage 1: Extract structured facts from raw tender text."""
    prompt = EXTRACTION_PROMPT.format(tender_text=tender_text)
    raw = _call_claude(prompt)
    data = _parse_json(raw)
    return ExtractedTender(**data)


def stage_2_score(extracted: ExtractedTender) -> ScoringResult:
    """Stage 2: Score extracted data against Semicon profile."""
    prompt = SCORING_PROMPT.format(
        extracted_json=extracted.model_dump_json(indent=2),
        today=date.today().isoformat(),
    )
    raw = _call_claude(prompt)
    data = _parse_json(raw)
    return ScoringResult(**data)


# ---------- Endpoints ----------

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_tender(req: AnalyzeRequest):
    """Full two-stage pipeline: extract → score."""
    extracted = stage_1_extract(req.tender_text)
    scoring = stage_2_score(extracted)
    return AnalyzeResponse(extracted=extracted, scoring=scoring)


@app.post("/extract", response_model=ExtractedTender)
async def extract_only(req: AnalyzeRequest):
    """Stage 1 only — useful for debugging extraction."""
    return stage_1_extract(req.tender_text)


@app.post("/score", response_model=ScoringResult)
async def score_only(extracted: ExtractedTender):
    """Stage 2 only — pass pre-extracted data for scoring."""
    return stage_2_score(extracted)


@app.post("/scan")
async def trigger_scan(days_back: int = 1, min_score: int = 20):
    """Ręcznie odpala skan BZP — filtruje CPV, analizuje, zwraca wyniki."""
    from scraper import run_scan
    results = run_scan(days_back=days_back, min_score=min_score)
    return {"found": len(results), "results": results}


@app.get("/results")
async def get_results():
    """Zwraca wyniki ostatniego skanu."""
    from pathlib import Path
    results_dir = Path("results")
    if not results_dir.exists():
        return {"results": []}
    files = sorted(results_dir.glob("scan_*.json"), reverse=True)
    if not files:
        return {"results": []}
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL}
