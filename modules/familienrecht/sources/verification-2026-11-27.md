# WP-135 source verification — 2026-11-27

Official consolidated HTML snapshots fetched locally with one request in flight,
two seconds between requests, 30-second request timeouts and no inference or embeddings.
Initial sandbox DNS failures were retried once through authorised network access.
All eight network-enabled requests succeeded. Local snapshots remain in /tmp;
hashes identify inspected bytes, not a redistribution of guideline material.

- [famfg](https://www.gesetze-im-internet.de/famfg/BJNR258700008.html): SHA256 `b2b1aea5000cdd33fc761d4adb88b123388903a9fb926717be054e02b0ae0a73`.
- [uvg](https://www.gesetze-im-internet.de/uhvorschg/BJNR011840979.html): SHA256 `dddd95e2ecbafeffbbdf4e7b35725916e463acda7cfa9d3741cf76a641323975`.
- [minuhv](https://www.gesetze-im-internet.de/minuhv/BJNR218800015.html): SHA256 `de8cb218becf53d24a172b8d869ffd7cb3c64a6f23a055f5e4b06aae385e1497`.
- [bgb1612a](https://www.gesetze-im-internet.de/bgb/__1612a.html): SHA256 `ab9706162365e1779ef0d091dd6987229346ac14748ba7e1e538c5fcef6e2089`.
- [bgb1612b](https://www.gesetze-im-internet.de/bgb/__1612b.html): SHA256 `e558182f7d1e0c36d59887c9095346af8c853d5e17dcc3a95be6fb84ff7f8866`.
- [bgb1613](https://www.gesetze-im-internet.de/bgb/__1613.html): SHA256 `ccd57260dd198892765b46397c8cd92a047ccb79b9c0ad99e6190ebf74ba4002`.
- [estg66](https://www.gesetze-im-internet.de/estg/__66.html): SHA256 `9d80c2433cd380b0ab32a5d0cd98135cf8b6ff5c2a868e3cfd43630549b2bd3f`.
- [zpo222](https://www.gesetze-im-internet.de/zpo/__222.html): SHA256 `bc7f8c65105881711e1aacbcbe49110d777ae7ce7d4e5d14dee6c829b1011583`.

## Parsed federal sources

- `famfg`: 1297 paragraph chunks parsed offline; expected operative sections/values found. No database ingestion or embeddings.
- `uvg`: 40 paragraph chunks parsed offline; expected operative sections/values found. No database ingestion or embeddings.
- `minuhv`: 2 paragraph chunks parsed offline; expected operative sections/values found. No database ingestion or embeddings.

## Findings and scope

FamFG §§16,63 link ordinary month arithmetic to ZPO §222. §63 starts with written notification, not the issue date. This module supports only confirmed formal domestic service of ordinary final decisions outside §113 proceedings. Informal notification, unsuccessful notification/five-month start, urgent/genehmigung proceedings (§63 Abs.2), §57 appealability, §§113/114/117 representation/grounds require individual review. No automatic one-year substitute period.

MinUhV §1 provides statutory minimum amounts for2026. BGB §1612a Abs.3 changes age bands at the start of the birthday month. The calculator requires age at month end for that month, not current age; excludes reaching majority in-month. BGB §1612b half-credit requires one parent fulfilling maintenance through care. No guideline percentage or self-retention table is included.

UVG §§1/2 require qualified eligibility, full child-benefit credit and complete same-month maintenance/orphan receipts. Older children need §1 Abs.1a checks. Partial months, age-band transitions and §2 Abs.4 income deductions are refused; no eligibility finding is made. §4 application/retroactivity is preparation guidance.

BGB §1613 Abs.1 yields only a conditional month start for a legally effective event and an existing claim at month start, not a filing deadline. Special need, hindrance, titles and other regimes are excluded.

## OQ-7 — unresolved, no bundled guideline data

Inspected the [publisher overview](https://www.olg-duesseldorf.nrw.de/infos/Duesseldorfer_Tabelle/index.php), [imprint](https://www.olg-duesseldorf.nrw.de/kontakt/impressum/index.php) and [reuse/copyright terms](https://www.olg-duesseldorf.nrw.de/kontakt/impressum/Haftungsausschluss/index.php). The terms discuss permission and possible third-party rights; they do not establish a reusable licence for this package. No permission is inferred and no third party was contacted. The module links externally instead of bundling the Düsseldorfer Tabelle, income-group percentages, self-retention or spousal-maintenance guideline values. Statutory amounts derive independently from MinUhV/BGB/EStG. OQ-7 remains open; source verification is not a legal-rights clearance.

Human review and live quality remain pending under D-071.
