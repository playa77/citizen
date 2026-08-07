# Compliance — Legal Status and AI Act Classification of Citizen

**Version:** 1.0.0 · **Date:** 2026-08-07
**Canonical version:** German · **Mirror:** [COMPLIANCE.md](COMPLIANCE.md) (canonical)
**Status:** Binding project classification (WP-60, Roadmap v2.0.0).

> **Not legal advice.** This document is an engineering-planning basis, not
> legal advice. It records the classification adopted by the project. The open
> legal questions collected in Roadmap v2.0.0 §8 are to be closed by external
> counsel, not by this document.

## 1. Purpose and Scope

This document is the **single authoritative source** for the legal
classification of Citizen under the EU AI Act (Regulation (EU) 2024/1689).
For every running instance it answers:

1. Is the operator a **provider**, a **deployer**, or neither?
2. Does the **development-phase exemption** (Art. 2(8)) or the personal-use
   framing apply?
3. Which obligations are **active** in the respective mode — and which are
   expressly **not** triggered?

The subject is the Citizen software and its generated outputs (analysis
reports, action-document drafts, chat answers). Not covered here: the
disclosure of AI authorship of the source code (`AI-USAGE.md`, WP-63) and the
legal notice to users (`DISCLAIMER_DE.md`).

## 2. Quick Answer: Obligations per Mode

The classification hinges on **one single switch**: `DEPLOYMENT_MODE`
(decision **D-019**, see `DECISIONS.md`). Three values:

| Mode | Meaning | Legal posture |
|---|---|---|
| `dev` | Author only, testing only, **synthetic data only** | Development phase, Art. 2(8) AI Act — obligations not triggered |
| `self` | Author only, on the author's own real Bescheide | Personal, non-professional use — obligations not triggered |
| `provider` | Deployed so that **any third party** can obtain an analysis | Author becomes **provider** (Art. 3(3)) — Art. 50 obligations active |

Legend: **A** = active (to be fulfilled) · **–** = not triggered · **D** = documentary (always relevant, no action duty)

| Obligation | Legal basis | `dev` | `self` | `provider` | Implementation |
|---|---|---|---|---|---|
| Provider/deployer determination | Art. 3(3)/(4) AI Act | – | – | A | this document (WP-60), D-019 |
| Development-phase posture held | Art. 2(8) AI Act | A | – | – | WP-62 (access control, synthetic-data guard, DEV-INSTANCE.md) |
| FOSS note: MIT does **not** exempt Art. 50 | Art. 2(12) AI Act | D | D | D | this document (WP-60) |
| Purpose: claimant-side, not authority-side | Annex III(5)(a) AI Act | A | A | A | WP-61 (self-assessment, purpose-drift lint), D-020 |
| AI-interaction notice to every natural person | Art. 50(1) AI Act | – | – | **A** | WP-64 |
| Machine-readable marking of all AI outputs | Art. 50(2) AI Act | – | – | **A** (deadline: **2026-12-02**, only if `provider` by then) | WP-65 |
| Disclosure for published text (public interest) | Art. 50(4) AI Act | – | – | – (not triggered: action documents are individual correspondence, not publication) | WP-65 (reasoning recorded in marker spec) |
| RDG single-case boundary (structural, pipeline-enforced) | § 2/§ 6/§ 8 RDG | – | – | A | WP-67, D-021 |
| GDPR: DPIA (Art. 35) + AVV chain (Art. 28) | GDPR | – (synthetic data only) | – (own data) | **A** (before the first real case) | WP-68 |
| Provider go/no-go gate | — (aggregate) | – | – | A (before first third-party use) | WP-69 |

**Quick answer in one sentence:** An instance in `dev` or `self` mode carries
no AI Act obligations and no GDPR/RDG triggers; an instance in `provider` mode
has the obligations marked **A** in the matrix active before the first real
third-party case may be processed — in particular Art. 50(1), Art. 50(2), the
RDG invariant, DPIA/AVV and the go/no-go gate.

## 3. The Switch: DEPLOYMENT_MODE

`DEPLOYMENT_MODE` is the technical embodiment of the provider/deployer
classification. Three values, one clear threshold:

* **`dev`** — the author develops and tests; exclusively synthetic data
  (goldset, test data) is processed. The instance is not made available to
  anyone. Rests on the Art. 2(8) development-phase exemption.
* **`self`** — the author uses the software on the author's own real
  Bescheide. This is personal, non-professional use; nothing is made available
  to third parties.
* **`provider`** — the software is deployed so that any third party (e.g.
  users of a social-advice center) can obtain an analysis. From this event
  onward the author is a **provider** within the meaning of Art. 3(3).

The switch is deliberately **explicit** and is not inferred from operational
details (e.g. whether authentication is configured) (D-019): the obligation
transition is one single auditable event, not a creeping state.

**Implementation status:** The switch is implemented in WP-66 in
`app/core/config.py`. Until then, the running instance is classified as mode
`dev` (development and testing by the author; hardening of the reachable
instance is WP-62).

## 4. Classification in Detail

### 4.1 Providers and Deployers (Art. 3(3)/(4))

- **Provider** (Art. 3(3)): a person that develops an AI system, or has it
  developed, and places it on the market or puts it into service under its
  own name.
- **Deployer** (Art. 3(4)): a person using the system, other than in a
  personal non-professional activity.

In `dev`/`self` the author is neither: nothing is placed on the market and
nothing is put into service for third parties. In `provider` the author is the
provider. A deploying social-advice center is a **deployer** within Art. 3(4)
and — in data-protection terms — the **controller** within Art. 4(7) GDPR.

### 4.2 Development Phase (Art. 2(8))

The AI Act does not apply to AI systems specifically developed and put into
service for the sole purpose of scientific research and development. The `dev`
mode is in this phase: reachable for testing, made available to no one. For
this classification to hold, the dev instance must satisfy three conditions
(hardened in WP-62): (1) access by the author only (VPN/mTLS or Basic Auth +
IP allowlist), (2) synthetic data only (startup assertion + ingest guard),
(3) no indexing (robots.txt, `noindex`) and a persistent development banner.

### 4.3 FOSS Exemption (Art. 2(12)) — and the Art. 50 Carve-Back

Citizen is MIT-licensed. AI systems released under free and open-source
licences are exempt from most of the AI Act — **but Art. 50 (transparency
obligations) is expressly carved back in** and remains applicable. The licence
therefore changes nothing about the fact that the Art. 50 obligations apply in
`provider` mode (AI-interaction notice, machine-readable output marking). In
`dev`/`self` mode Art. 50 does not apply because there is **no provision to
third parties** — not because of the licence.

### 4.4 Not High-Risk (Annex III(5)(a))

The Annex III(5)(a) high-risk trigger concerns AI systems used by authorities
to **evaluate the benefit eligibility** of persons. By its declared intended
purpose (D-020), Citizen is a **claimant-side** self-help and advisor-assistance
tool — it is not intended for authority-side evaluation. The full
self-assessment is documented in WP-61 and guarded against copy drift by a
purpose-drift lint.

## 5. Deadlines and Triggering Events

| Event / deadline | Effect |
|---|---|
| **Provision to third parties** (`DEPLOYMENT_MODE=provider`) | Switches on the Art. 50 obligations as well as the GDPR and RDG requirements (see section 2) |
| **2026-12-02** (end of the grace period for Art. 50(2)) | **Binding only if** `provider` applies by then: the machine-readable marking must be complete by that date. Otherwise it gates the later deployment. |
| **First real third-party case** | Processing only after: purpose guard green (WP-61), notice live (WP-64), marking live (WP-65), RDG invariant tested (WP-67), DPIA + AVV chain in place (WP-68), go/no-go gate signed (WP-69). |

## 6. Adjacent Legal Regimes

### 6.1 GDPR

The GDPR is the most underestimated regime for operation. Bescheide of benefit
claimants routinely contain **special-category data** (Art. 9 GDPR: health,
disability); the data subjects are vulnerable persons. Consequences:

- **`provider`:** A **Data Protection Impact Assessment (DPIA, Art. 35)** is
  very likely mandatory; an **AVV chain (Art. 28)** must be in place before
  the first real case: author as processor → EU inference as sub-processor
  (profile `eu-avv`) → advice center as controller. Implementation: WP-68.
- **`self`:** The author processes the author's own data; no DPIA/AVV duty.
  The existing safeguards (pseudonymization, egress guard) remain active
  (defense in depth).
- **`dev`:** Synthetic data only; no processing of personal data. The
  synthetic-data guard (WP-62) prevents real data from entering the dev
  instance.

### 6.2 RDG (German Legal Services Act)

A system that examines one identified person's specific Bescheid sits near the
line of *Rechtsdienstleistung in konkreter fremder Angelegenheit* (§ 2 RDG).
The project position (D-021):

- Every output is **legal information plus building blocks** requiring human
  adjudication; no output is presented as a completed legal assessment of the
  individual case.
- Unadjudicated legal assertions appear in action documents as
  `[BITTE PRÜFEN]` placeholders — technically enforced, not merely declared
  (WP-67).
- For advice-center use, the § 6/§ 8 RDG frame (unentgeltliche
  Rechtsdienstleistung / anerkannte Beratungsstellen) is documented (WP-67).

## 7. Validity and Change Management

- This document is part of Roadmap v2.0.0 (WP-60) and anchored in the decision
  ledger via decisions D-019 and D-022 (and, in their work packages, D-020 and
  D-021).
- Changes to the intended purpose, deployment form or target group require a
  review and a version change of this document (semantic versioning).
- Open legal questions that cannot be closed technically are collected in
  Roadmap v2.0.0 §8.

## References

- `docs/roadmap-v2.0.0.md` — Phases P6–P8, obligation matrix (§5)
- `DECISIONS.md` — D-019, D-020, D-021, D-022
- `DISCLAIMER_DE.md` / `DISCLAIMER_EN.md` — legal notice for users
- `README.md` — section „Rechtlicher Status"
- `AI-USAGE.md` — disclosure of AI authorship of the source code (WP-63)
