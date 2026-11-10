# Proposal: Bulk-Beziehungen für die Topologie (Agent: frontend)

**Status:** offen — Topologie limitiert auf 200 Ressourcen (UI-Hinweis +
gesamtes Detail-Endpunkte-Abfragen).
**Betreff:** `/api/v1/resources/{resource_id}` liefert Beziehungen nur pro
Ressource; die Topologie (`frontend/src/features/topology/TopologyPage.tsx`)
muss deshalb für bis zu 200 Ressourcen je einen Detail-Request starten
(`useResourceDetailsAll`).

## Motivation

- Die Topologie-UI benötigt **alle** Beziehungen des Inventars
  (`ResourceRelationOut[]`) in einem Rutsch.
- Pro Ressource ein Request ergibt für 200 Ressourcen 200 HTTP-Calls pro
  Ladevorgang (aktuell per `Promise.allSettled`, Fehlschläge werden als
  `failed` gezählt und ehrlich angezeigt — aber nicht skalierbar).
- Bei >200 Ressourcen bricht die UI heute ab (hartes Limit, sichtbar
  gekennzeichnet).

## Vorschlag (Diff-Plan)

Neuer Pfad:

| Methode | Pfad | Berechtigung | Beschreibung |
| ------- | ---- | ------------ | ------------ |
| GET | `/api/v1/resources/relations` | viewer+ (`resources.read`) | Alle Beziehungen des Inventars, paged (`Paged_ResourceRelationOut`), optional filterbar nach `relation_type`, `source_resource_id`, `target_resource_id` |

Schemata: `Paged_ResourceRelationOut` (bestehende Envelope über dem
bestehenden Schema `ResourceRelationOut` — **kein** neues Ressourcen-Schema).

Alternativ (falls Paging unpraktikabel): `GET /resources/relations?full=true`
liefert die komplette Relation-Liste ohne Paging, begrenzt auf 5000 Einträge,
mit Header `X-Total-Count` — für Homelab-Größen (<<5000 Beziehungen) der
einfachere Weg.

## Impact

- **Frontend:** `useResourceDetailsAll` wird ersetzt durch einen einzigen
  `useResourceRelations()`; Topologie-UI, Filters (api/manual/inferred) und
  das „skipped"-Zählen bleiben unverändert. Das 200-Limit entfällt.
- **Keine Datenänderung:** Relationen entstehen weiterhin ausschließlich im
  Backend (Adapter/Inventar); der Endpoint ist ein reiner Lese-Verzeichnispfad.
- **Performance:** ein Index auf `(source_resource_id, target_resource_id)`
  genügt; `SELECT … FROM relations` ohne Joins (Namen `source_name/
  target_name` sind bereits in den Relationen persistiert).
