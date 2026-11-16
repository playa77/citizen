# Citizen — Roadmap v2.0.0: Legal Posture, Compliance & Provider Readiness

<!-- Version: 2.0.0 | 2026-08-07 -->
<!-- STATUS 2026-11-16: SUPERSEDED for new work by docs/roadmap-v3.0.0.md
     (free public path, module architecture; D-034…D-041). Kept unchanged as
     the record of P6–P8 and because DISCLAIMER_*.md / DEV-INSTANCE.md cite
     its WP numbers. Open items carried over: roadmap v3.0.0 § 2 (C-1…C-5). -->
<!-- §7 below ("no new legal areas", "no UI") was the scope of THIS roadmap;
     it is lifted for new work by D-036/D-038 (modules) and P12 (UI). -->

<!-- STATUS 2026-08-25: planning document, kept as written. Note that the
     deliverables `COMPLIANCE.md`, `COMPLIANCE-EN.md` and `STATEMENT.md`
     referenced below were later consolidated into DISCLAIMER_DE.md /
     DISCLAIMER_EN.md (v2.0.0) — read those file names as "the disclaimer
     documents". -->
<!-- Supersedes: citizen-roadmap-v1.0.0 (P0–P5, WP-00…WP-54) for all NEW work. -->
<!-- Roadmap v1.0.0 remains the record for hardening work already completed. -->
<!-- Canonical version source: pyproject.toml (per D-9). Baseline: v0.4.5. -->
<!-- Phase/WP numbering continues the v1.0.0 decade scheme: P6→WP-60s, P7→WP-70s, P8→WP-80s. -->
<!-- Decisions continue the append-only ledger in /DECISIONS.md from D-018 → D-019+. -->

---

## 0. Baseline and Trigger

### 0.1 Baseline

This roadmap builds on the v0.4.5 codebase delivered by roadmap v1.0.0: a
working, eval-gated analysis pipeline (9 stages), deterministic Fristen and
SGB-II calculation engines, pseudonymization + `eu-avv` inference profile,
goldset + eval harness, and a versioned legal disclaimer (`DISCLAIMER_DE.md`
v1.1.0) enforced by a first-run acknowledgment gate. Data handling, retrieval,
and correctness hardening are substantially in place.

### 0.2 What is missing (the gap this roadmap closes)

The repository has **no AI-Act posture**. A full-tree search returns zero
references to Art. 50 VO (EU) 2024/1689, to the provider/deployer distinction
(Art. 3(3)/(4)), to the development-phase exemption (Art. 2(8)), to Annex III
high-risk classification, or to the national implementing act (KI-MIG,
BNetzA). The existing disclaimer frames the software as *personal,
non-professional* use — which is coherent with the Art. 2(8) development
posture but does **not** address the obligations that attach the moment the
system is deployed for third parties, which is exactly the endpoint the
project's own `STATEMENT.md` names ("in jeder Sozialberatungsstelle").

Citizen is not merely software *built with* AI; when deployed it is software
that *itself provides an AI system generating text output about a person's
individual legal situation*. That is the regulated object, and its legal
weight changes discontinuously at one event: **the transition from the
author's own development/testing to deployment for third-party users.**

### 0.3 Scope of this roadmap

"Newly needed features" here means precisely the runtime features that
compliance forces into existence — an AI-interaction notice, machine-readable
output marking, a deployment-mode switch, and dev-instance access control.
This roadmap deliberately contains **no speculative product features** (no new
legal areas, no new UI surfaces, no chat un-parking). Product feature work is
listed as explicitly out of scope in §7. Everything below is either a legal
obligation, the minimal feature that discharges it, or the transition event
that triggers it.

### 0.4 The governing model

Three legal regimes bear on the deployed system, in descending order of how
often they are underestimated:

1. **DSGVO** — the most binding and most underestimated. Bescheide of
   claimants routinely contain special-category data (Art. 9: health,
   disability, sometimes more). Deployed use is systematic evaluation of
   vulnerable data subjects → a DPIA (Art. 35) is very likely mandatory, and
   an AVV chain (author as provider → EU inference sub-processor → advice
   center as controller) must exist before the first real case.
2. **RDG** — the highest *residual* litigation risk specific to this product.
   A system that examines one identified person's specific Bescheid sits near
   the line of *Rechtsdienstleistung in konkreter fremder Angelegenheit*
   (§ 2 RDG). This is where Citizen would realistically be attacked, not at
   Art. 50.
3. **KI-VO (AI Act)** — the obligation set the user asked about. Materially
   light for a deployer (a notice line), heavier for a *provider* (output
   marking, interaction notice), and dominated by classification: whether Dan
   becomes a provider, and whether the purpose statement keeps the system out
   of Annex III.

The FOSS license does not help here: Art. 2(12) exempts free/open-source AI
systems from most of the Regulation **but expressly carves Art. 50 back in.**
MIT licensing removes nothing from the Art. 50 analysis.

---

## 1. Decisions to Ratify (append to /DECISIONS.md)

These are proposed for ratification at the start of P6. Format matches the
existing ledger (`D-XXX R{1|2} — Date` / Decision / Rejected / Rationale).

### D-019 R2 — proposed 2026-08-07
**Decision:** Introduce a single authoritative `DEPLOYMENT_MODE` setting with
three values — `dev`, `self`, `provider` — as the technical embodiment of the
provider/deployer classification. `dev` (author, testing, synthetic data
only) and `self` (author using it on the author's own real Bescheide) rest on
the Art. 2(8) development exemption and the personal-use framing respectively;
`provider` (deployed so that any third party can obtain an analysis) makes the
author a provider under Art. 3(3) and switches on all Art. 50 obligations.
**Rejected:** (a) Inferring provider status implicitly from whether auth is
configured — too fragile, and couples a legal determination to an operational
accident. (b) Treating every deployment as `provider` unconditionally — would
impose provider obligations on the author's own machine, which the personal-use
and development exemptions do not require.
**Rationale:** The obligation set is discontinuous at one event; a single
explicit switch makes that event auditable and prevents silent drift into
provider status. Every compliance feature in P7 keys off this one setting.

### D-020 R1 — proposed 2026-08-07
**Decision:** Fix the system's stated intended purpose (Zweckbestimmung,
Art. 3(12)) as **claimant-side self-help and advisor assistance** and prohibit
any documentation, pitch, or UI copy that describes Citizen as a tool used
*by or on behalf of* an authority to evaluate benefit eligibility.
**Rejected:** Leaving the purpose statement implicit. The Annex III(5)(a)
high-risk trigger is authority-side eligibility evaluation; the classification
turns on the declared purpose, so an undeclared purpose is an unmanaged risk.
**Rationale:** Keeping the declared purpose claimant-side is what keeps the
system out of the high-risk regime (Kapitel III). This is a cheap, decisive
guardrail, but only if it is written down and enforced against copy drift.

### D-021 R2 — proposed 2026-08-07
**Decision:** Treat the RDG single-case boundary as a hard product invariant:
every output is Rechtsinformation plus building blocks requiring human
adjudication; no output is presented as a completed legal assessment of the
individual case, and the generated action documents remain drafts with
`[BITTE PRÜFEN]` placeholders for anything unadjudicated. The provider-mode
deployment path for advice centers is documented against § 6/§ 8 RDG
(unentgeltliche Rechtsdienstleistung / anerkannte Beratungsstellen), not
against a claim that the tool itself renders no Rechtsdienstleistung.
**Rejected:** Relying solely on the existing § 2 RDG disclaimer text. A
disclaimer does not change what the software functionally does; the invariant
has to live in the product behavior, not only in the notice.
**Rationale:** This is the highest residual legal risk. The mitigation must be
structural (human-in-the-loop enforced by the pipeline) and must survive the
transition to advice-center use, where the RDG analysis actually shifts.

### D-022 R1 — proposed 2026-08-07
**Decision:** Add `AI-USAGE.md` to the repository root documenting that the
codebase is predominantly AI-generated, and add a one-line notice to the
README. This is voluntary content-authorship transparency, distinct from and
additional to the Art. 50 runtime obligations.
**Rejected:** Folding it into `DISCLAIMER_DE.md`. The disclaimer governs the
*legal character of the software's output*; authorship of the *source* is a
separate concern and belongs in its own file.
**Rationale:** Cheap, honest, and forecloses a later "undisclosed" objection.
Also carries the § 2 Abs. 2 UrhG note that AI-generated code without personal
intellectual creation is not copyright-protected, which is relevant to anyone
forking or commercializing the repo.

---

## 2. Phase P6 — Legal Posture & Compliance Foundation

Documentation and classification layer plus one small guard. Almost no
production code. This phase is a prerequisite for P7 and P8: it decides *what*
Citizen legally is, so the later phases can implement it.

### WP-60 — Compliance baseline document and classification
**Objective:** Establish the single source of truth for Citizen's legal
classification under the KI-VO.
**Tasks:**
1. Create `COMPLIANCE.md` (German canonical, English mirror
   `COMPLIANCE-EN.md`) covering: the provider/deployer determination keyed to
   `DEPLOYMENT_MODE`; the Art. 2(8) development-phase posture; the Art. 2(12)
   FOSS carve-in for Art. 50; and a plain-language statement of which
   obligations are active in each mode.
2. Record decisions D-019 and D-022 in `/DECISIONS.md`.
3. Add a "Rechtlicher Status" section to the README pointing to `COMPLIANCE.md`.
**Deliverables:** `COMPLIANCE.md`, `COMPLIANCE-EN.md`, README section,
`/DECISIONS.md` entries.
**Depends on:** none.
**Exit criteria:** A reader can determine, from `COMPLIANCE.md` alone, exactly
which obligations apply to a given running instance and why.
**Reversibility:** R1 (documentation).

### WP-61 — Annex III high-risk self-assessment
**Objective:** Document, defensibly, that Citizen is not a high-risk system in
its declared purpose, and guard the declaration against drift.
**Tasks:**
1. Write the Annex III(5)(a) assessment into `COMPLIANCE.md`: the high-risk
   trigger is authority-side eligibility evaluation; Citizen is claimant-side;
   therefore not caught — conditional on the declared purpose (D-020).
2. Record decision D-020.
3. Add a documentation-lint check (`scripts/check_purpose_drift.py`, Python)
   that scans `README*.md`, `STATEMENT.md`, `COMPLIANCE*.md`, and any
   `docs/pitch*` for authority-side phrasing (a small configurable
   deny-phrase list, e.g. "für Jobcenter", "für Behörden", "im Auftrag der <!-- purpose-drift: allow -->
   Verwaltung") and fails CI on a match. Full error handling; verbose
   per-match output with file and line.
**Deliverables:** Annex III section in `COMPLIANCE.md`, D-020 entry,
`scripts/check_purpose_drift.py`, CI wiring.
**Depends on:** WP-60.
**Exit criteria:** CI fails if any tracked document describes Citizen as an
authority-side tool.
**Reversibility:** R1.

### WP-62 — Dev-instance Art. 2(8) hardening
**Objective:** Bring the internet-reachable development VPS unambiguously
inside the Art. 2(8) exemption: reachable for testing, not *provided* to
anyone.
**Tasks:**
1. Access control: put the dev instance behind WireGuard or Tailscale as the
   primary posture; document mTLS or HTTP Basic Auth + IP allowlist as the
   fallback. The instance must be reachable by the author for testing and by
   no one else.
2. Enforce synthetic-data-only on the dev instance: a startup assertion that
   refuses to run in `DEPLOYMENT_MODE=dev` unless a
   `CITIZEN_SYNTHETIC_DATA_ONLY=true` flag is set, plus an ingest-time check
   that rejects documents not tagged as goldset/synthetic when that flag is on.
   Python, full error handling.
3. Serve `X-Robots-Tag: noindex` and a `robots.txt` disallow on the dev
   instance.
4. In-app development banner (persistent, non-dismissible) in `dev` mode:
   `ENTWICKLUNGSINSTANZ — Testbetrieb mit synthetischen Daten. Keine Nutzung
   für reale Fälle. Ausgaben sind nicht belastbar.`
5. Create `devdocs/DEV-INSTANCE.md`: purpose, who has access, nature of test
   data, explicit statement of no real-world use, dated and versioned.
**Deliverables:** access-control runbook in `DEV-INSTANCE.md`, synthetic-data
guard code + tests, noindex headers, dev banner, `DEV-INSTANCE.md`.
**Depends on:** WP-60 (needs `DEPLOYMENT_MODE`; may land the setting here if
WP-66 has not yet).
**Exit criteria:** The dev instance is not publicly usable, cannot ingest real
data, is not indexable, and carries a documented no-real-use posture.
**Reversibility:** R2 (adds a startup assertion and an ingest guard; interface
preserved).

### WP-63 — Repository authorship transparency
**Objective:** Voluntary content-authorship disclosure, separate from Art. 50.
**Tasks:**
1. Create `AI-USAGE.md` (German canonical + English section): predominantly
   AI-generated code; human origin of design, requirements, acceptance;
   review posture (inspected, functionally checked, not a security audit); the
   § 2 Abs. 2 UrhG copyright note; and the statement that source code falls
   outside Art. 50(2) marking per the Commission's 20 July 2026 guidelines and
   outside the Art. 50(4) disclosure obligation.
2. Add the one-line README notice pointing to it.
3. Record D-022.
**Deliverables:** `AI-USAGE.md`, README line, D-022 entry.
**Depends on:** none (can run in parallel with WP-60).
**Exit criteria:** Authorship is disclosed; no per-file or per-directory
duplication.
**Reversibility:** R1.

---

## 3. Phase P7 — Provider-Readiness Runtime

The runtime features Art. 50 requires **once `DEPLOYMENT_MODE=provider`**. All
three key off the single switch from D-019. In `dev`/`self` they are inert or
minimal; in `provider` they are enforced.

### WP-66 — Deployment-mode switch (implement first in P7)
**Objective:** Make D-019 real in code.
**Tasks:**
1. Add `DEPLOYMENT_MODE` to `app/core/config.py` (`dev` | `self` | `provider`;
   default `dev`). Lazy-loaded like the other settings.
2. Expose it read-only via the existing `meta` route group
   (`GET /api/v1/meta/version` extended, or a new
   `GET /api/v1/meta/deployment-mode`) so the frontend and any auditor can see
   the active posture.
3. Surface the active mode in the UI header, next to the existing Rechtsstand
   and profile banners.
4. Startup log line stating the active mode and which obligation set is
   consequently active.
**Deliverables:** config field, meta endpoint, header indicator, tests.
**Depends on:** WP-60 (classification); may co-land with WP-62.
**Exit criteria:** The active legal posture is a single configured value,
visible in the UI and API, logged at startup.
**Reversibility:** R2 (new setting + endpoint; existing contracts preserved).

### WP-64 — Art. 50(1) AI-interaction notice
**Objective:** Inform every natural person, at first interaction, that they are
interacting with an AI system — distinct from the legal disclaimer.
**Tasks:**
1. A concise KI-system notice, machine- and human-readable, shown at the first
   entry surface in `provider` mode: web UI (before first analysis), and as a
   field in the initial SSE/JSON response of `/api/v1/analyze`,
   `/api/v1/cases/{id}/chat`, and `/api/v1/intake/start`.
2. Keep it separate from the `X-Disclaimer-Ack` gate: the disclaimer governs
   *no-legal-advice*; this notice governs *this-is-an-AI-system*. Both can be
   satisfied at the same first-run step but are recorded independently.
3. In `dev`/`self` mode the notice may be reduced to a static line (the sole
   user is the author).
4. Version the notice text and expose it via `meta`, mirroring the existing
   disclaimer version/text endpoints.
**Deliverables:** notice text (versioned), UI surface, API response field,
`meta` endpoints, tests.
**Depends on:** WP-66.
**Exit criteria:** No third-party user can reach an analysis result in
`provider` mode without having been told they are using an AI system.
**Reversibility:** R2.

### WP-65 — Art. 50(2) machine-readable output marking
**Objective:** Mark all AI-generated output as artificially generated, in a
machine-readable form, for `provider` mode.
**Tasks:**
1. Define a versioned provenance marker spec (`docs/provenance-marker.md`):
   what is marked, the marker schema, and how it appears per output type.
2. Text exports (JSON/Markdown case export, action documents Widerspruch /
   § 44 SGB X / § 25 SGB X): embed a machine-readable provenance block
   (generator identity, model/profile, timestamp, marker spec version) and a
   visible human-readable line. For any rendered/PDF output, additionally
   attach C2PA-style content credentials where the export format supports it.
3. Analysis reports shown in-app: carry the same provenance metadata in the
   payload.
4. Scope carve-out, documented in the marker spec: pure source code and short
   machine-readable strings are outside Art. 50(2) per the Commission's
   guidelines; the action documents and analysis reports are the marked
   surface.
5. Note on Art. 50(4): the generated action documents are **not** text
   published to inform the public on matters of public interest — they are
   individual correspondence — so the Art. 50(4) *deployer* disclosure
   obligation does not attach to them. Do not over-implement a public-interest
   disclosure here; record the reasoning in the marker spec so it is not
   re-litigated later.
**Deliverables:** `docs/provenance-marker.md`, marking in all generators and
exporters, C2PA attachment where supported, tests asserting every
`provider`-mode output carries a valid marker.
**Depends on:** WP-66.
**Exit criteria:** Every artifact leaving the system in `provider` mode is
machine-readably marked as AI-generated; the marker spec is versioned.
**Reversibility:** R2 (extends generators/exporters; output schemas gain
fields, existing fields preserved).
**External deadline:** This is the **only** obligation in this roadmap with a
fixed calendar date rather than an event trigger. The Art. 50(2) provider
marking obligation carries a grace period to **2026-12-02**. If Citizen is in
`provider` mode by then, WP-65 must be complete by that date. If it is not yet
deployed to third parties, the deadline does not bind and WP-65 gates the
deployment instead.

---

## 4. Phase P8 — RDG & Deployment Hardening

The real litigation-risk mitigation and the DSGVO gate for the advice-center
deployment. This phase is what actually permits flipping `DEPLOYMENT_MODE` to
`provider`.

### WP-67 — RDG boundary hardening
**Objective:** Make the RDG single-case invariant structural, not merely
declared.
**Tasks:**
1. Audit every output path for language that could read as a completed legal
   assessment of the individual's case; downgrade to Rechtsinformation +
   building-block framing where found.
2. Enforce, in the document generators, that any legal assertion not bound to
   a user-adjudicated finding renders as `[BITTE PRÜFEN]` — verify this
   invariant with tests, not only in code review.
3. Document the § 6/§ 8 RDG posture for the advice-center path in
   `COMPLIANCE.md`: unentgeltliche Rechtsdienstleistung and anerkannte
   Beratungsstellen as the frame under which advisors may act, and the limits
   on the author's own role.
4. Record D-021.
**Deliverables:** output-language audit notes, generator invariant tests,
RDG section in `COMPLIANCE.md`, D-021 entry.
**Depends on:** WP-60.
**Exit criteria:** The pipeline cannot emit an unadjudicated legal assertion
as settled; the RDG posture is documented for both self-help and advice-center
use.
**Reversibility:** R2.
**Note:** This is the item where an external consult is warranted. The
single-case boundary and the § 3a UWG question (see §8) are genuinely
unsettled; one paid hour with a media/legal-tech lawyer is the proportionate
mitigation, and this WP is where it belongs.

### WP-68 — DSGVO deployment gate (DPIA + AVV chain)
**Objective:** Satisfy the data-protection preconditions before any real
third-party case is processed.
**Tasks:**
1. Extend the existing `docs/datenschutz/` templates (VVT, AVV checklist) into
   a completed DPIA (Art. 35 DSGVO) for `provider`-mode use, given
   special-category data (Art. 9) and vulnerable data subjects.
2. Document the AVV chain: author-as-provider → EU inference sub-processor
   (under the `eu-avv` profile) → advice center as controller; provide an AVV
   template for the author↔advice-center relationship.
3. Verify the egress guard and pseudonymization posture against the DPIA's
   stated data flows (re-use existing WP-31 egress-guard machinery; this is
   verification, not greenfield).
**Deliverables:** completed DPIA, AVV chain documentation + template, egress
verification note.
**Depends on:** WP-66; runs alongside WP-67.
**Exit criteria:** A DPIA exists, the AVV chain is documented end to end, and
the data flows match what the guard enforces.
**Reversibility:** R1 (documentation + verification of existing controls).

### WP-69 — Provider-mode deployment checklist and go/no-go
**Objective:** A single gate that must be green before `DEPLOYMENT_MODE` is set
to `provider` for a real advice-center pilot.
**Tasks:**
1. `devdocs/PROVIDER-GO-NOGO.md`: a checklist aggregating the exit criteria of
   WP-60…WP-68 into one signable page (classification recorded, purpose guard
   green, Art. 50(1) notice live, Art. 50(2) marking live, RDG invariant
   tested, DPIA complete, AVV chain in place).
2. A `scripts/preflight_provider.py` (Python) that asserts the machine-checkable
   subset at startup when `DEPLOYMENT_MODE=provider` (notice configured, marker
   spec present, synthetic-only flag OFF and real-data handling controls ON,
   egress guard active) and refuses to boot in provider mode otherwise. Full
   error handling; each failed check named explicitly.
**Deliverables:** `PROVIDER-GO-NOGO.md`, `scripts/preflight_provider.py`, tests.
**Depends on:** WP-60…WP-68.
**Exit criteria:** Provider mode cannot be entered unless the machine-checkable
controls pass and the human checklist is signed.
**Reversibility:** R2.

---

## 5. Compliance Obligation Matrix

| Obligation | Legal basis | Triggered when | WP | Artifact | Mode |
|---|---|---|---|---|---|
| Provider/deployer classification | Art. 3(3)/(4) | Always (determines the rest) | WP-60 | `COMPLIANCE.md`, D-019 | all |
| Development-phase exemption held | Art. 2(8) | Dev/test only | WP-62 | `DEV-INSTANCE.md`, guards | dev |
| Not authority-side high-risk | Annex III(5)(a) | Always; purpose-dependent | WP-61 | Annex III assessment, purpose-drift lint, D-020 | all |
| FOSS does not exempt Art. 50 | Art. 2(12) | Always | WP-60 | `COMPLIANCE.md` note | all |
| AI-interaction notice | Art. 50(1) | Third-party deployment | WP-64 | notice text + surfaces | provider |
| Machine-readable output marking | Art. 50(2) | Third-party deployment | WP-65 | `provenance-marker.md`, marked outputs | provider |
| Public-interest text disclosure | Art. 50(4) | **Not triggered** (individual correspondence, not published) | WP-65 note | reasoning recorded | n/a |
| RDG single-case boundary | § 2 / § 6 / § 8 RDG | Always; shifts at deployment | WP-67 | generator invariant, RDG section, D-021 | all |
| DPIA | Art. 35 DSGVO | Third-party deployment | WP-68 | completed DPIA | provider |
| AVV chain | Art. 28 DSGVO | Third-party deployment | WP-68 | AVV docs + template | provider |
| Provider go/no-go gate | — (aggregates above) | Before provider pilot | WP-69 | `PROVIDER-GO-NOGO.md`, preflight | provider |
| Repo authorship transparency | voluntary (§ 2 Abs. 2 UrhG note) | Always | WP-63 | `AI-USAGE.md` | all |

---

## 6. Sequencing and the One Hard Date

Recommended order:

1. **P6 first, in full.** It is cheap, mostly documentation, and it decides
   what the system legally is. Nothing downstream is correct until the
   classification (WP-60) and purpose fix (WP-61) exist. WP-62 (dev-instance
   hardening) is the one item worth doing immediately regardless of the rest —
   it protects the current running VPS.
2. **WP-66 before the rest of P7.** The mode switch is the spine every other
   provider feature hangs on.
3. **P7 (WP-64, WP-65) and P8 (WP-67, WP-68) can proceed in parallel** once
   WP-66 lands, since they touch different surfaces (runtime notices/marking
   vs. RDG framing and data-protection docs).
4. **WP-69 last** — it is the gate, and it can only be green when everything it
   aggregates is done.

The only fixed calendar date is **2026-12-02** (Art. 50(2) provider-marking
grace-period end), and it binds **only if** Citizen is in `provider` mode by
then. Every other obligation here is triggered by the deployment event, not by
a date: as long as `DEPLOYMENT_MODE` stays `dev`/`self`, the provider
obligations are dormant and WP-69's gate is what stands between the current
posture and them activating. This means the roadmap has no external time
pressure until a real advice-center pilot is imminent — the pressure is the
gate, not the clock.

---

## 7. Explicitly Out of Scope

To hold the line against scope creep, the following are **not** part of this
roadmap and must not be smuggled into its work packages:

- New legal areas or promotion of any experimental area to verified.
- Un-parking chat or Electron (roadmap v1.0.0 D-5 stands).
- Any new analysis capability, retrieval change, or model-staffing change.
- Multi-tenancy beyond what a single advice-center pilot strictly requires.
- Monetization, accounts, or hosted-service infrastructure.
- UI redesign beyond the two indicators WP-66 and (optionally) WP-64 add.

If any of these becomes necessary, it earns its own roadmap entry with its own
justification — it does not ride in on a compliance work package.

---

## 8. Open Legal Questions (require external counsel, not code)

These are genuinely unsettled and cannot be closed by engineering. They are
recorded so they are decided deliberately, not by default.

1. **§ 3a UWG marktverhalten.** Whether Art. 50 KI-VO is a market-conduct rule
   whose breach is privately actionable under § 3a UWG is not settled by case
   law; the norm is too new. The `provider`-mode marking (WP-65) is the
   mitigation regardless of how this resolves, because it removes the
   underlying breach.
2. **RDG single-case boundary.** Whether examining one identified person's
   specific Bescheid crosses from Rechtsinformation into Rechtsdienstleistung
   in konkreter fremder Angelegenheit is the sharpest question for the product
   and the place it would realistically be challenged. WP-67 mitigates
   structurally; a paid consult is the proportionate additional step.
3. **Advice-center RDG frame.** Which exact § 6/§ 8 RDG basis a given advice
   center relies on (and therefore what the author may and may not supply to
   it) depends on the center's own recognition status. WP-68's AVV work
   surfaces this per partner.
4. **Self-review under Art. 50(4) editorial exemption.** Not relevant to the
   generated documents (they are not public-interest publications), but flagged
   because the author's separate Substack posture (handled outside this
   repository) rests on it.

None of these blocks P6 or the dev-instance hardening. They gate only the
provider pilot, and they are the reason WP-69 requires a human signature and
not merely a passing preflight script.

---

*Changes to this document follow semantic versioning. This is roadmap v2.0.0;
it supersedes roadmap v1.0.0 for new work only and does not alter the record of
completed P0–P5 work. Legal characterizations herein are engineering-planning
inputs, not legal advice; the open questions in §8 are exactly the points on
which the author is not a lawyer and should obtain one.*
