# WP-130 source and evidence record

Module 0.2.0 · source retrieval 2026-11-26 · human review deferred under D-071.
Thirty successful official statute/announcement snapshots are identified by URL,
retrieval date and SHA-256 in `sources.json`. Retrieval is an engineering source
check, not human legal approval or deployment corpus ingestion.

## Implemented statutory anchors

| Source | Implemented scope and boundary |
|---|---|
| [ZPO §§ 692, 694](https://www.gesetze-im-internet.de/zpo/__692.html) | Domestic actual-service two-week action period. Opposition may remain possible until an enforcement order is issued; no absolute cutoff claim. Form guidance does not assert that every natural person must use a form. |
| [ZPO §§ 700, 339](https://www.gesetze-im-internet.de/zpo/__700.html) | Domestic enforcement-order opposition only. Foreign/public service is not silently assigned the domestic period. |
| [ZPO § 222](https://www.gesetze-im-internet.de/zpo/__222.html), BGB §§ 187–188 | Event-based day counting and weekend/holiday rollover; explicit service date, type, mode and region required by dossier rules. |
| [ZPO § 850c](https://www.gesetze-im-internet.de/zpo/__850c.html) | Qualified monthly attachment net; up to five-or-more table column, rounded income, protected shares and fully attachable excess. No maintenance/special-order calculation. |
| [2025 announcement](https://www.gesetze-im-internet.de/pf_ndfreigrbek_2025/BJNR06E0A0025.html), [2026 announcement](https://www.gesetze-im-internet.de/pf_ndfreigrbek_2026/BJNR0500A0026.html) | Versioned annual monthly amounts covering July 2025–June 2027, not the unadjusted amounts printed in the base statute. |
| [ZPO §§ 899, 902](https://www.gesetze-im-internet.de/zpo/__899.html) | P-account basic ceiling plus qualified actual maintenance increases. Other benefits, carryovers and special allowances require review. § 850k concerns conversion; § 903 concerns proof/certification. |
| [BGB §§ 195, 197, 199, 201](https://www.gesetze-im-internet.de/bgb/__199.html) | Explicitly qualified ordinary/titled claims only, including start and longstop rules; no legal qualification inferred by the arithmetic engine. |
| [BGB §§ 204, 212](https://www.gesetze-im-internet.de/bgb/__204.html), § 193 | Suspension, restart and uncertain legal facts cause refusal; the qualified place-of-performance calendar must be supplied for limitation rollover. |
| [RDG §§ 13e, 13f](https://www.gesetze-im-internet.de/rdg/__13e.html), [RVG § 13 and annexes](https://www.gesetze-im-internet.de/rvg/__13.html), UStG § 12 | Qualified undisputed, untitled collection-cost plausibility bound. Fee-case/transition/VAT eligibility must be explicit; no blanket reimbursement entitlement. |
| [InsO §§ 304, 305](https://www.gesetze-im-internet.de/inso/__305.html) | Appointment preparation, creditor/claim breakdown, income/assets and suitable-counselling referral. No insolvency filing or issued certificate. |
| [GDPR Art. 15, official BMF reproduction](https://ao.bundesfinanzministerium.de/ao/2025/Datenschutz-Grundverordnung/inhalt.html) | Guarded own-data access request, not automated legal claims or disclosure of third-party data. EUR-Lex access was challenged; no bypass/retry was attempted. |

Short source quotations and reference dates are retained in parameter-row
`notes` and `basis`, using the existing parameter schema. Non-expiring rule
snapshots start on the checked date without inventing retrospective coverage;
annual attachment parameters retain explicit legal validity limits. Parameter
status remains `proposed`; copy and schema evidence remain `draft`.

## Deterministic evidence

`goldset/reports/attachment-table-check.json` records comparison with every
monthly cell of both official tables, at both ends of each income interval:
3,906 cells, 7,812 boundary assertions, zero mismatches. This includes the
zero-income bands (the earlier 3,894-cell check counted the other bands).
Independent literal tests also cover excess above the table cap, dependent
increases, missing facts, legal qualifications, costs and date boundaries.

Dossier and plain-language reports under `goldset/reports/` identify the core,
module, goldset and schema versions and the measured gate results. These are
local deterministic reports; no live pipeline quality score is fabricated.

## Operational acceptance and deferred review

The core now supports all five required statute types through its existing
catalog/parser/storage paths. Disposable PostgreSQL tests exercise the new
constraint values. Actual deployment corpus download, embeddings/readiness and
live inference remain installation operations; they were not run against a
configured user database or inference account. Synthetic fixtures and source
snapshots do not stand in for those operations. Human review and verified
promotion are deferred until all modules are implemented (D-071).
