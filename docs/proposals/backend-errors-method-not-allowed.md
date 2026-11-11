# Vorschlag: `method_not_allowed` in den eingefrorenen ErrorCode-Enum aufnehmen (Agent 1, R1)

- **Status:** offen (R1 behält das frozen Mapping, keine Code-Ergänzung)
- **Autor:** Agent 1 (backend-auth), Branch `feature/auth`
- **Betroffener Bereich:** `backend/app/errors.py` (frozen Mapping + Enum), `backend/contracts/openapi.v1.json` (frozen `ErrorCode`-Enum), `docs/api-contracts.md`
- **Verletzte Regel:** keine — dieser Vorschlag existiert, weil die Doku einen Code verspricht, der im frozen Enum fehlt (AGENTS.md §4)

## 1. Diskrepanz

Die Doku `docs/api-contracts.md` (Zeile 51) listet `method_not_allowed` (405)
als vorgesehenen maschinellen Code:

> Weitere Codes: `conflict` (409), `rate_limited` (429),
> `method_not_allowed` (405) — siehe `app/errors.py::ErrorCode`.

Der **frozen** `ErrorCode`-Enum in `backend/contracts/openapi.v1.json`
(Section `components.schemas.ErrorCode`) enthält ihn **nicht**:

```
enum: validation_error, unauthenticated, forbidden, not_found,
      conflict, rate_limited, not_configured, not_implemented,
      adapter_error, internal_error
```

Konsequenz: `app/errors.py::_STATUS_CODE_MAP` mappt 405 auf den
**bestehenden** Code `not_found` (mit der 405-spezifischen Message
„Methode für diese Ressource nicht erlaubt"). Das ist konsistent mit dem
frozen Enum, widerspricht aber der Doku.

## 2. Was in R1 getan wurde (keine Contract-Änderung)

- Das frozen Mapping bleibt: **405 → `not_found`** (frozen Enum, keine neue
  Enum-Mitglied, keine OpenAPI-Regeneration).
- `tests/test_error_handling_r1.py::test_405_uses_error_envelope` belegt das
  tatsächliche R1-Verhalten: 405 liefert die einheitliche Error-Envelope
  `{"error": {"code": "not_found", ...}}`.
- Die Doku-Diskrepanz wird hier dokumentiert, statt den Contract stillschweigend
  zu ändern.

## 3. Vorgeschlagene Contract-Änderung (für Freigabe)

1. `ErrorCode.METHOD_NOT_ALLOWED = "method_not_allowed"` zum Enum in
   `app/errors.py` hinzufügen.
2. `_STATUS_CODE_MAP[405]` auf `METHOD_NOT_ALLOWED` umleiten.
3. `backend/contracts/openapi.v1.json` neu generieren
   (`scripts/generate-openapi.py`) → `ErrorCode`-Enum um den Wert ergänzt.
4. `docs/api-contracts.md` in die Haupt-Tabelle (statt Fußnote) aufnehmen.
5. `tests/test_contracts_snapshot.py` das neue Snapshot mitnehmen.

## 4. Warum jetzt nicht (Entscheidung R1)

- Der `ErrorCode`-Enum ist ein **frozen Contract** und wird von Agent 2
  (Frontend, generierter Client) und Agent 5 (QA, Contract-Tests)
  konsumiert. Eine Enum-Erweiterung ist abwärtskompatibel, aber ein
  Contract-Change und gehört in ein koordiniertes Release, nicht in
  Agent 1's Feature-Branch.
- Bis zur Freigabe ist das aktuelle Mapping (`not_found`) **korrekt und
  stabil** — Clients dürfen sich darauf verlassen.

## 5. Auswirkungen der Freigabe

- Frontend-Client (Agent 2): `method_not_allowed` wird als zusätzlicher
  Enum-Wert verfügbar (additiv, nicht brechend).
- QA (Agent 5): Contract-Test um den neuen Wert erweitern.
- Keine Migration, keine Datenmodell-Änderung, keine Routen-Änderung.

## 6. Entscheidung

- [ ] Freigabe: `method_not_allowed` als eigene Enum-Konstante + 405-Mapping
- [ ] Ablehnung: Doku `docs/api-contracts.md` stattdessen korrigieren
  (405 → `not_found` als dokumentiertes Verhalten)
- [ ] Beide: Code **und** Doku angleichen (empfohlen, wenn die Semantik
  „Method vs. Route unterscheiden" für Clients/Proxies gewünscht ist)

Empfehlung: **Freigabe** — für Proxies/Monitoring/Clients ist die
Unterscheidung „Endpunkt unbekannt" (404) vs. „falsche Methode auf bekanntem
Pfad" (405) fachlich sinnvoll und in der Doku bereits so intendiert.

Freigabe durch: Integrationsreview / Koordination.
