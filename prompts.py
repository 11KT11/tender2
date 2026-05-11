EXTRACTION_PROMPT = """# Rola: Ekstraktor danych przetargowych

Przeanalizuj treść ogłoszenia przetargowego i wyodrębnij WYŁĄCZNIE fakty.
NIE oceniaj, NIE punktuj, NIE interpretuj dopasowania do żadnej firmy.

## Co wyodrębnić:

1. **subject** — Co dokładnie zamawiają? (technologia, produkt, usługa). Zwięźle, 1-2 zdania.
2. **tech_categories** — Wybierz WSZYSTKIE pasujące z listy:
   ["EMS", "PCBA", "SMT", "THT", "reballing", "cable_harness", "laser", "optoelectronics",
    "components", "stencil", "tape_converting", "engineering", "design", "PCB_bare",
    "IT_commodity", "office_supplies", "SaaS", "software", "mechanical", "construction",
    "catering", "transport", "other"]
   Jeśli nic nie pasuje, użyj ["other"] i opisz w subject.
3. **required_certs** — Certyfikaty/normy wymagane w przetargu:
   ["AS9100", "ISO_13485", "ISO_9001", "AQAP", "ABW", "MON", "NCAGE", "IPC", "UL", "CE", "other"]
4. **buyer_sector** — Branża zamawiającego:
   "military" | "aviation" | "medical" | "telecom" | "industrial" | "public_admin" | "energy" | "other"
5. **formal_conditions**:
   - deadline: termin składania ofert (format YYYY-MM-DD jeśli możliwe)
   - deposit: wadium (kwota + waluta)
   - penalties: informacja o karach umownych
   - experience_required: wymagane doświadczenie/referencje
6. **location** — Województwo/miasto realizacji
7. **estimated_value** — Wartość szacunkowa jeśli podano

## WAŻNE:
- Jeśli informacja NIE występuje w tekście, wstaw null.
- Odpowiedz WYŁĄCZNIE validnym JSON-em. Bez markdown, bez komentarzy, bez ```json```.

## Treść przetargu:
{tender_text}"""


SCORING_PROMPT = """# Rola: Analityk dopasowania przetargowego — Semicon Sp. z o.o.

## Profil Semicon:
- Rdzeń biznesu: EMS (montaż kontraktowy SMT/THT), reballing BGA, produkcja wiązek kablowych
- Produkty własne: Moduły laserowe, szablony SMT, taśmy techniczne (converting)
- Dystrybucja: Komponenty elektroniczne, optoelektronika, diody laserowe
- Certyfikaty: AS9100 (lotnictwo), ISO 13485 (medycyna), NCAGE (NATO/wojsko), ISO 9001
- Lokalizacja: Województwo mazowieckie

## Wyekstrahowane dane przetargu:
{extracted_json}

## Reguły scoringu:

### DYSKWALIFIKACJA → wynik 0, is_relevant: false
Zastosuj jeśli tech_categories zawiera WYŁĄCZNIE elementy z:
["IT_commodity", "office_supplies", "SaaS", "software", "construction", "catering", "transport"]
(tzn. żadnej kategorii technicznej bliskiej profilowi Semicon)

### SCORING POZYTYWNY (sumuj punkty, max 100):
- tech_categories zawiera DOWOLNY z ["EMS","PCBA","SMT","THT","reballing","cable_harness"] → +40
- tech_categories zawiera DOWOLNY z ["laser","optoelectronics","components","stencil","tape_converting"] → +25
- required_certs zawiera DOWOLNY z ["AS9100","ISO_13485","AQAP","ABW","MON","NCAGE"] → +20
- tech_categories zawiera DOWOLNY z ["engineering","design"] → +10
- location zawiera "mazowieckie" lub "Warszawa" → +5

### MODYFIKATORY RYZYKA (dodaj do risk_factors):
- deadline < 14 dni od dziś ({today}) → "tight_deadline"
- penalties wskazują na kary > 10% wartości → "harsh_penalties"
- experience_required wymaga referencji których Semicon może nie mieć → "missing_references"
- estimated_value > 5 000 000 PLN → "high_value_scrutiny"

### STRATEGIC ADVANTAGE:
- Jeśli required_certs pokrywa się z certyfikatami Semicon → opisz przewagę
- Jeśli buyer_sector to "military"/"aviation"/"medical" → Semicon ma naturalną przewagę
- W przeciwnym razie → "Brak wyraźnej przewagi"

## ODPOWIEDZ WYŁĄCZNIE validnym JSON (bez markdown, bez ```):
{{
  "match_score": <int 0-100>,
  "is_relevant": <bool>,
  "reasoning": "<max 2 zdania, po polsku>",
  "key_requirements": ["<max 3 kluczowe wymogi>"],
  "strategic_advantage": "<opis lub Brak wyraźnej przewagi>",
  "risk_factors": ["<lista ryzyk lub pusta>"]
}}"""
