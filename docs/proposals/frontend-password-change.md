# Proposal: Passwortwechsel-Endpunkt (Agent: frontend)

**Status:** offen — Einstellungen-Seite zeigt „Passwortwechsel erforderlich",
kann ihn aber nicht ausführen (kein Endpunkt im R0-Vertrag).
**Betreff:** `must_change_password` wird bei Bootstrap und User-Anlage gesetzt,
aber es gibt keinen Endpunkt, um das eigene Passwort zu ändern.

## Motivation

- Bootstrap-Admin und neu angelegte User starten mit
  `must_change_password: true` (frozen Contract). Ohne Wechselpfad bleibt
  dieses Flag ewig `true` — die UI zeigt in `SettingsPage` einen Hinweis, der
  nicht entkräftet werden kann.
- Security (AGENTS.md §8): Initialpasswörter (auch Admin) sollen sofort nach
  Erst-Login geändert werden.

## Vorschlag (Diff-Plan)

Neuer Pfad:

| Methode | Pfad | Berechtigung | Beschreibung |
| ------- | ---- | ------------ | ------------ |
| POST | `/api/v1/auth/password` | authed + CSRF | eigenes Passwort ändern; Body: `{ current_password, new_password }`; setzt `must_change_password=false`; Session bleibt gültig (oder optional neu ausgestellt) |

Schemata:

- `PasswordChangeRequest`: `{ current_password: string (8–200), new_password:
  string (8–200) }`.
- `PasswordChangeResponse`: `{ message: "ok" }`.
- Fehler-Codes: `422 validation_error` (Schwäche zu schwach, z. B. zu kurz),
  `403 forbidden` (falsches `current_password`).

Optionale (empfohlene) Ergänzung — admin kann Passwort eines anderen User
resetten (z. B. für inaktivierte/vergessene Accounts):

| Methode | Pfad | Berechtigung | Beschreibung |
| ------- | ---- | ------------ | ------------ |
| POST | `/api/v1/users/{user_id}/password-reset` | admin + CSRF | setzt `must_change_password=true` + temporary token (out-of-band) |

## Impact

- **Frontend:** `SettingsPage` erhält ein Passwortformular (nur, wenn
  `must_change_password === true` oder freiwillig); `AuthProvider` bleibt
  unverändert (Session-Prüfung über `/auth/me`).
- **Audit:** `action="auth.password_changed"` (Details maskiert).
- **Security:** konstanter Zeitabgleich bei `current_password`-Prüfung (wie
  Login/Bootstrap); Rate-Limit; Argon2id-Hash bleibt unverändert.
