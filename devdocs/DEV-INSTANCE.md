# Dev-Instanz — Betriebsdokumentation (Art. 2(8) KI-VO)

**Version:** 1.1.1 · **Stand:** 2026-11-16 (WP-93: Goldset-Pfad)
**Zugehöriges Work Package:** WP-62 (Roadmap v2.0.0)
**Rechtsgrundlage:** Art. 2(8) VO (EU) 2024/1689 (Entwicklungsphasen-Freistellung)

> **Kein Rechtsrat.** Dieses Dokument ist eine Engineering-Planungsgrundlage,
> keine Rechtsberatung. Maßgeblich für die Klassifizierung ist
> `DISCLAIMER_DE.md`, Teil C.

---

## 1. Zweck

Die internet-erreichbare Entwicklungsinstanz dient **ausschließlich dem Autor**
zum Testen, Demonstrieren und Weiterentwickeln von Citizen. Sie ist bewusst
**nicht** so bereitgestellt, dass Dritte Analysen erhalten können. Sie liegt
damit in der Entwicklungsphasen-Freistellung des Art. 2(8) KI-VO.

**Ausdrückliche Feststellung:** Die Instanz wird **nicht** für reale Fälle
genutzt. Es werden **keine echten Bescheide** verarbeitet. Alle Ausgaben dieser
Instanz sind nicht belastbar und dürfen nicht als Grundlage für
Rechtsentscheidungen verwendet werden.

## 2. Zugriffskontrolle (Runbook)

### Primär: WireGuard oder Tailscale

Die Instanz ist **nicht** über das öffentliche Internet erreichbar; der Zugriff
läuft ausschließlich über ein privates Mesh-VPN:

- **WireGuard:** Einrichtung als Site-to-Site oder Roadwarrior-Tunnel; nur der
  Autoren-Endpoint ist im `AllowedIPs`-Bereich der Instanz. Der Reverse-Proxy
  (nginx) bindet an die VPN-Schnittstelle oder lässt nur VPN-IPs zu.
- **Tailscale:** Instanz in einem privaten Tailnet mit `--advertise-tags` und
  ACLs, die nur den Autor zulassen (`allow: [daniel]`; `deny: [*]` für
  externe Nutzer).

Nach Änderungen an der VPN-Konfiguration ist die Erreichbarkeit mit einem
Test durch den Autor zu verifizieren (z. B. `curl https://<dev-host>/health`).

### Fallback: mTLS oder HTTP Basic Auth + IP-Allowlist

Falls VPN nicht verfügbar ist, ist einer der folgenden Wege zwingend:

1. **mTLS:** Client-Zertifikat des Autors am Reverse-Proxy (nginx
   `ssl_verify_client on; ssl_client_certificate ...`); alle anderen
   Requests werden mit `403` abgelehnt.
2. **HTTP Basic Auth + IP-Allowlist:** nginx `auth_basic` mit starkem
   Passwort **und** `allow <IP>`-Liste nur für die Autoren-IP(s) mit
   abschließendem `deny all;`.

Ein Betrieb ohne eine dieser Maßnahmen ist **nicht** zulässig: Die Instanz
muss für den Autor erreichbar und für niemanden sonst sein.

## 3. Nur synthetische Daten (technisch erzwungen)

Die dev-Instanz verarbeitet ausschließlich synthetische Daten. Dies wird
technisch durchgesetzt:

- **Startup-Assertion:** `DEPLOYMENT_MODE=dev` ohne
  `CITIZEN_SYNTHETIC_DATA_ONLY=true` verweigert den Start
  (`app/services/dev_guard.py`, `check_dev_synthetic_data_startup()`).
- **Ingest-Guard:** Bei aktiver Posture werden Dokument-Uploads ohne
  `X-Document-Tag: synthetic` oder `X-Document-Tag: goldset` mit `403`
  abgelehnt (`check_synthetic_data_request()`; an `/api/v1/ingest`, den
  Chat-Dokument-Uploads und der Konversations-Erstellung mit Datei).

**Was zählt als synthetisch:** Goldset-Fälle (`modules/*/goldset/`),
generierte Testdokumente, jede vom Autor ausdrücklich als Testdatensatz
markierte Datei. Echte Bescheide, echte Anträge oder echte
Behördenkorrespondenz gehören **nicht** auf diese Instanz; für die
Verarbeitung eigener realer Bescheide dient ein lokaler Betrieb im Modus
`self`.

## 4. Nicht indexierbar

- Die Anwendung setzt `X-Robots-Tag: noindex, nofollow` auf allen Antworten
  im Modus `dev` (`app/middleware/dev_headers.py`).
- `/robots.txt` liefert im Modus `dev` `Disallow: /` aus.

## 5. Entwicklungs-Banner

Der Dienst liefert im Modus `dev` einen dauerhaften Banner-Text über
`GET /api/v1/meta/deployment-mode` (Feld `dev_banner`):

> **ENTWICKLUNGSINSTANZ — Testbetrieb mit synthetischen Daten. Keine Nutzung
> für reale Fälle. Ausgaben sind nicht belastbar.**

Clients, die die API für Dritte zugänglich aufbereiten, müssen diesen Banner
unabhängig von der Disclaimer-Bestätigung dauerhaft ausweisen.

## 6. Zugriff

| Rolle | Zugriff |
|---|---|
| Autor | Vollzugriff über VPN (primär) bzw. mTLS / Basic-Auth + IP (Fallback) |
| Dritte (inkl. Beratungsstellen, Behörden) | Kein Zugriff — weder über das Netzwerk noch über die API |

## 7. Keine reale Nutzung

- Es werden keine echten Fälle verarbeitet.
- Ausgaben sind ausschließlich für Entwicklungs- und Testzwecke bestimmt.
- Es werden keine personenbezogenen Daten Dritter verarbeitet.
- Für einen späteren Einsatz für Dritte ist der Modus `provider`
  (WP-64…WP-69) mit Go/No-Go-Gate (WP-69; Gate-Dokument noch zu erstellen)
  erforderlich — diese Instanz wird dafür nicht verwendet.

## 8. Änderungsdienst

Änderungen an Zugriffskontrolle, Datenposture oder Zweckbestimmung erfordern
eine Fassungsänderung dieses Dokuments (semantische Versionierung) und eine
erneute Prüfung der Klassifizierung (siehe `DISCLAIMER_DE.md`, Teil C.7).

## Referenzen

- `DISCLAIMER_DE.md` (Teil C) — Klassifizierung und Pflichten-Matrix
- `docs/roadmap-v2.0.0.md` — WP-62
- `app/services/dev_guard.py` — Startup- und Ingest-Guards
- `app/middleware/dev_headers.py` — Noindex-Header
- `app/api/routes/meta.py` — `GET /api/v1/meta/deployment-mode`
