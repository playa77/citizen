# Citizen — Legal Notice, Disclaimer, Project Statement and AI Act Classification

**Version:** 2.0.0 · **Date:** 2026-08-25

**Author:** www.github.com/playa77

**Repository:** https://github.com/playa77/citizen

This document consolidates the legal notice and disclaimer, the project
statement, and the project's compliance/AI Act classification into a single
English-language version (German canonical version:
[DISCLAIMER_DE.md](DISCLAIMER_DE.md)). It replaces the former standalone
documents `DISCLAIMER_EN.md` (v1.1.0), `STATEMENT.md` (v1.0.0) and
`COMPLIANCE-EN.md` (v1.1.0).

It contains legal notices and disclaimers. It does not replace or modify the
applicable open-source license terms unless expressly stated.

This software is provided under the MIT License and **gratuitously**. By
providing, accessing, or using it, no fee, exchange, or service relationship
is created.

To the extent this document contains contractual terms, they apply only to the
maximum extent permitted by applicable mandatory law.

Changes to this document follow semantic versioning; the change history is at
the end of this document.

---

## Part A — Why This Project Exists

### What it is

Citizen today is a prototype: an analysis pipeline that reads German social-law
benefit notices (Bescheide), binds every statement to the statutory text,
recomputes benefit calculations deterministically, and determines deadlines to
the exact day. There is a versioned golden set of verified test cases against
which every change is measured. Known limitations exist, and they live in the
repository rather than under the rug. That is the honest current state:
working, unpolished, measurable — and not yet a product.

### What it should be

A person holds a notice their livelihood depends on and, within minutes,
receives four answers: **What does it say? Is it correct? By when must I
respond? What do I do now?** — traceably evidenced, recalculated to the cent,
dated to the day, in plain language. Free of charge. Open source. Without
their data leaving Europe. And the same tool sits in every social-advice
center, turning a three-quarter-hour initial review into ten minutes with
statutory citations.

### Why

In 2025, more than half a million objections were filed against Jobcenter
notices. Roughly one in three succeeded. In more than 42,000 cases the agency
had demonstrably misapplied the law. This rate has been stable for years — it
is not an outlier, it is a systemic condition. And it strikes asymmetrically:
on one side an administration that produces notices mechanically millions of
times; on the other a single person with a one-month deadline, no lawyer, and
often without the language of the notice — literally and figuratively.

A constitutional state is a promise: that rights do not depend on who you are
or what you can afford. That promise is worth only as much as its
enforceability. A right you do not know about, a deadline you miss, a
calculation you cannot check — on paper that is a right; in reality it is not.

A second reason reaches beyond social law. We are at the beginning of a
transition in which machine intelligence becomes basic infrastructure — and
transitions have a treacherous property: **they freeze the distribution of
power as it exists at the moment of transition.** Administrations will
automate their side; that is certain. If the citizen's side does not receive
the same class of tools, the existing asymmetry will not merely be preserved
but enshrined at a higher level. Citizen is my contribution to the opposing
thesis: the same capability, the same thoroughness, the same tirelessness —
in the hands of the weaker party. It is a small, concrete answer to the big
question of whom the machines should serve: everyone. Or no one.

And a third, sober reason from the perspective of complex systems: an error
rate stable at one third for years means the system's feedback loop is broken.
Every erroneous notice nobody objects to is an error signal that never
arrives. Tools that make objections more precise, better evidenced, and more
frequent are therefore not an attack on the administration — they are the
repair of its corrective mechanism. An administration whose errors are
reliably found improves. In the end, both sides of the desk benefit.

### Principles

**Recalculability over trust.** Whatever can be deterministic — deadlines,
amounts, citations — is computed deterministically and verified. The language
model is a tool, not an authority.

**Honesty about limits.** If a notice is lawful, Citizen says so. False hope
is no help; it is a second affront. Uncertain legal questions are marked as
uncertain, not smoothed away.

**Data stays with the person.** Pseudonymization before every processing step,
inference exclusively in Europe under data processing agreements, local data
storage. Only what is technically enforced is claimed.

**The human decides.** Citizen informs, evidences, recomputes, and supplies
building blocks. Assessment, decision, and signature belong to humans — the
affected person themselves or advisors authorized to advise.

**Openness as auditability.** MIT license, public golden set, versioned
correction of its own errors. A tool that finds administrative errors must
subject itself to the same scrutiny.

### What it is not

Not legal advice — legal information and self-help. Not a startup — there is
nothing to earn from people in existential need, and none is attempted here.
Not a declaration of war on Jobcenter staff — most work under conditions that
produce errors; this tool targets errors, not people.

### Invitation

If you want to review legally, validate cases, contribute code, or trial the
tool in an advice center: issues and pull requests are open. The best form of
criticism of this project is a golden-set case it answers incorrectly.

*Figures: objection and litigation statistics of the German Federal Employment
Agency 2025 (147,213 of 476,728 decided objections revised; 42,303 cases of
erroneous application of the law; Jobcenter Essen: 53.7% error rate in decided
objections, May 2026).*

---

## Part B — Legal Notice and Disclaimer

### B.1 Nature of the Software

This repository contains personal, bespoke software developed primarily for
the author's own use, documentation, experimentation, and personal reference.

The software has not been designed, tested, audited, certified, or approved
for production use, commercial use, public deployment, safety-critical
systems, security-critical systems, medical systems, financial systems, legal
practice, or professional legal advice, or any other environment where
failure, malfunction, data loss, incorrect outputs, or security issues could
cause harm.

Public availability of this repository does not constitute a product offering,
professional service, legal service, recommendation, warranty, or
representation that the software is suitable for any particular purpose.

### B.2 No Legal Advice

This software is a technical tool for informational, educational,
experimental, and personal reference purposes only.

It does not constitute legal advice, professional consultation, legal
representation, or a substitute for advice from a qualified lawyer or other
qualified professional.

The author does not act in specific third-party matters within the meaning of
§ 2 (1) of the German Legal Services Act (Rechtsdienstleistungsgesetz, RDG).
The software operates schematically according to predetermined rules,
procedures, and verification steps; no case-specific legal review by the
author takes place. Users who apply the software to their own documents and
their own affairs handle their own legal matters (self-assistance). Use of the
software in the context of advising or assisting third parties is permitted
only to those entities and persons who are authorized to do so under the RDG
or other provisions; responsibility for the existence of such authorization
and for the advice itself rests solely with those entities and persons.

No attorney-client relationship, mandate, fiduciary relationship, advisory
relationship, or other professional legal relationship is formed by accessing,
installing, running, or using this software.

You must not rely on this software as the sole basis for legal decisions,
filings, applications, objections, appeals, communications with authorities,
contractual decisions, litigation strategy, or any other legally relevant
action.

Always consult qualified legal counsel before taking or refraining from any
action with legal consequences.

### B.3 AI-Generated Content and Accuracy

Outputs may be generated using artificial intelligence, large language models,
automated retrieval systems, ranking systems, citation systems, or other
automated processes.

Even where the software attempts to use evidence-binding, retrieval
augmentation, source references, citation tracking, or similar mechanisms,
outputs may be inaccurate, incomplete, misleading, outdated, hallucinated, or
based on incorrect interpretation of statutes, regulations, administrative
guidance, case law, contracts, policies, or other materials.

The author does not warrant or represent that any output is correct, complete,
current, legally valid, admissible, reliable, or suitable for any specific
use.

You are solely responsible for independently verifying all outputs against
official, current, and authoritative sources before using them. This includes,
where applicable, checking original statutes, regulations, administrative
materials, court decisions, official publications, deadlines, procedural
requirements, and professional legal advice.

### B.4 Data Processing, Data Protection, and Inference Profiles

The software stores data locally. To the extent the software uses external
services for processing (in particular language model and embedding services),
this is done exclusively through configurable, versioned **inference
profiles**. The currently active profile can be queried via the API endpoint
`GET /api/v1/meta/active-profile` and is indicated in generated documents.

The software provides the following profiles in particular:

- **eu-avv** (default for use within organizations): Before every external
  processing operation, direct identifiers (in particular names, addresses,
  reference numbers, bank details, contact data, dates of birth) are replaced
  by a technically enforced pseudonymization stage. Transmission takes place
  exclusively to endpoints in the European Union that are permitted in the
  profile configuration, on the basis of a data processing agreement (DPA).
  A technical egress guard blocks transmissions to non-permitted destinations
  as well as transmissions of recognized plaintext identifiers.
- **extern-openrouter** (self-assistance and development operation):
  Pseudonymized input data may be transmitted to external providers,
  including to servers outside your country or legal jurisdiction, including
  regions with different data protection laws and data protection standards.
- **on-prem** (if configured): no external transmission.

Pseudonymization covers direct identifiers according to the documented rule
set. Residual risks — in particular, potential identifiability from the
remaining case context as well as misdetection of individual items — cannot be
ruled out. Pseudonymized data remain personal data within the meaning of the
GDPR.

The author does not control third-party providers and does not — even if a
data processing agreement exists — warrant or guarantee their security
measures, availability, data storage, deletion practices, use for training
purposes, confidentiality, regulatory compliance, or compliance with the GDPR
or other data protection laws. The selection, vetting, and contractual
engagement of external providers is the responsibility of whoever operates the
software.

Anyone who applies the software to **their own** documents and data as a data
subject decides on this under their own responsibility and consents under the
respectively active profile. Anyone who processes data of **third parties**
with the software (in particular advisory centers and other organizations) is
themselves the controller within the meaning of the GDPR and is solely
responsible for determining and complying with all obligations under
applicable data protection law, confidentiality law (in particular the German
social data protection provisions of § 35 SGB I, §§ 67 ff. SGB X),
professional law, consumer protection law, and information security law —
including the legal basis, information of data subjects, required consent,
data processing agreements, technical and organizational measures, records of
processing activities, and, where required, a data protection impact
assessment.

Special categories of personal data, confidential information, privileged
information, trade secrets, client data, and other sensitive information may
only be entered or processed if the above prerequisites are met.

This disclaimer is not a privacy policy.

You are solely responsible for any data you input, process, transmit, store,
or disclose using the software.

### B.5 No Warranty

To the maximum extent permitted by applicable law, this software is provided
"as is" and "as available", without warranty of any kind, whether express,
implied, statutory, or otherwise.

Without limiting the foregoing, the author makes no warranty or representation
that the software:

- is error-free, secure, complete, accurate, or up to date;
- will operate without interruption;
- is compatible with any particular system, platform, provider, model, API, or
  environment;
- is free from viruses, vulnerabilities, or harmful components;
- will meet your requirements or expectations;
- will produce legally correct, complete, or usable results;
- will preserve confidentiality, privilege, or data protection compliance; or
- is suitable for production, commercial, professional, legal,
  security-critical, or safety-critical use.

To the maximum extent permitted by applicable law, all implied warranties,
including warranties of merchantability, fitness for a particular purpose,
title, and non-infringement, are disclaimed.

### B.6 Limitation of Liability

The software is provided gratuitously. To the extent permitted by law,
liability is therefore additionally governed by the legal standards applicable
to gratuitous transfers and gifts.

To the maximum extent permitted by applicable law, the author, contributors,
maintainers, and affiliates, if any, shall not be liable for any claims,
damages, losses, liabilities, costs, or expenses arising out of or in
connection with the software, its outputs, or its use, including without
limitation:

- direct or indirect damages;
- incidental, special, consequential, exemplary, or punitive damages;
- loss of profits, revenue, business, goodwill, or anticipated savings;
- loss, corruption, disclosure, or unauthorized processing of data;
- loss of use, downtime, system failure, or security incidents;
- incorrect, incomplete, outdated, or misleading outputs;
- missed deadlines, defective filings, rejected applications, adverse
  administrative decisions, sanctions, penalties, benefit reductions,
  repayment claims, legal fees, litigation costs, or adverse judgments;
- unauthorized access to, use of, or alteration of your transmissions,
  content, prompts, documents, or data;
- conduct, content, services, APIs, models, or systems of third parties; or
- claims by third parties.

This applies regardless of the legal theory, whether based on contract, tort,
negligence, strict liability, warranty, statutory duty, professional duty, or
otherwise, even if the author has been advised of the possibility of such
damages.

The above limitations of liability apply only to the extent permitted by
applicable mandatory law.

In particular, liability remains unaffected for:

- willful misconduct;
- gross negligence, to the extent exclusion is not permitted by law;
- injury to life, body, or health;
- mandatory provisions of product liability law;
- fraudulent concealment of a defect;
- an expressly assumed guarantee; and
- all other cases in which liability cannot be excluded or limited by law.

If the user is a consumer within the meaning of § 13 BGB (German Civil Code),
the above limitations apply only insofar as they do not violate mandatory
consumer protection provisions.

### B.7 User Responsibility and Assumption of Risk

You are solely responsible for evaluating whether the software and its outputs
are suitable for your intended use.

If you access, clone, download, install, build, run, modify, deploy, interact
with, or otherwise use the software, you do so at your own risk.

You are solely responsible for all decisions, filings, applications,
objections, appeals, communications, submissions, legal actions,
administrative actions, business decisions, or other actions taken or omitted
based on outputs from this software.

You are responsible for taking appropriate precautions, including independent
legal review, professional advice, code review, security review, testing,
backups, verification of sources, checking deadlines, checking procedural
requirements, and compliance with applicable laws and regulations.

### B.8 No Support or Maintenance

The author has no obligation to provide support, maintenance, updates, bug
fixes, security fixes, documentation, responses to issues, responses to pull
requests, or any other assistance.

The publication of this repository does not create any service relationship,
consulting relationship, fiduciary relationship, employment relationship,
partnership, professional relationship, or other special relationship between
the author and any user.

### B.9 Third-Party Components and Services

This repository may contain, reference, call, or depend on third-party
software, libraries, models, APIs, services, tools, data, or documentation.

Third-party components and services are provided under their own terms,
licenses, policies, and privacy practices. You are solely responsible for
reviewing and complying with those terms.

The author is not responsible for third-party components or services and makes
no warranty or representation regarding them.

### B.10 Governing Law and Jurisdiction

To the extent legally permissible, this disclaimer shall be governed by the
laws of the Federal Republic of Germany, excluding the United Nations
Convention on Contracts for the International Sale of Goods.

If you are a consumer habitually resident in another country, including a
member state of the European Union or the United States of America, this
choice of law does not deprive you of any mandatory consumer protection rights
or other mandatory rights under the laws of your country of habitual
residence.

To the extent legally permissible, if the user is a merchant, a legal entity
under public law, or a special fund under public law, the courts at the
author's place of residence or registered office in Germany shall have
jurisdiction. Mandatory statutory venues remain unaffected.

### B.11 Severability

If any provision of this disclaimer is held to be invalid, unlawful, or
unenforceable, the remaining provisions shall remain in effect to the maximum
extent permitted by law.

The invalid, unlawful, or unenforceable provision shall be interpreted,
limited, or replaced to the extent necessary to make it valid and enforceable
while preserving its intended purpose as closely as legally possible.

### B.12 Acknowledgment

By accessing, installing, running, interacting with, or using this software,
you confirm that you have read and understood this disclaimer and that you use
the software at your own risk.

The software is implemented as an API. Analyses and other protected operations
are performed only when each request carries acknowledgment of the currently
valid version (header `X-Disclaimer-Ack`, obtainable via
`GET /api/v1/meta/disclaimer/version`); after a version change, renewed
acknowledgment is required. The acknowledged version is recorded per analysis
run together with timestamp and application version in the local audit log.
The acknowledged version is authoritative at any given time. Documents and
reports generated by the software indicate the underlying versions in the
footer.

If you do not agree with this disclaimer, do not use the software.

---

## Part C — Compliance: Legal Status and AI Act Classification

> **Not legal advice.** This part is an engineering-planning basis, not legal
> advice. It records the classification adopted by the project. The open
> legal questions collected in Roadmap v2.0.0 §8 are to be closed by external
> counsel, not by this document.

### C.1 Purpose and Scope

This part is the **single authoritative source** for the legal classification
of Citizen under the EU AI Act (Regulation (EU) 2024/1689). For every running
instance it answers:

1. Is the operator a **provider**, a **deployer**, or neither?
2. Does the **development-phase exemption** (Art. 2(8)) or the personal-use
   framing apply?
3. Which obligations are **active** in the respective mode — and which are
   expressly **not** triggered?

The subject is the Citizen software and its generated outputs (analysis
reports, action-document drafts, chat answers). Not covered here: the
disclosure of AI authorship of the source code (WP-63, planned) — the legal
notice to users is Part B of this same document.

### C.2 Quick Answer: Obligations per Mode

The classification hinges on **one single switch**: `DEPLOYMENT_MODE`
(decision **D-019**, see `DECISIONS.md`). Three values:

| Mode | Meaning | Legal posture |
|---|---|---|
| `dev` | Author only, testing only, **synthetic data only** | Development phase, Art. 2(8) AI Act — obligations not triggered |
| `self` | Author only, on the author's own real Bescheide | Personal, non-professional use — obligations not triggered |
| `provider` | Deployed so that **any third party** can obtain an analysis | Author becomes **provider** (Art. 3(3)) — Art. 50 obligations active |

Legend: **A** = active (to be fulfilled) · **–** = not triggered · **D** =
documentary (always relevant, no action duty)

| Obligation | Legal basis | `dev` | `self` | `provider` | Implementation |
|---|---|---|---|---|---|
| Provider/deployer determination | Art. 3(3)/(4) AI Act | – | – | A | this part (WP-60), D-019 |
| Development-phase posture held | Art. 2(8) AI Act | A | – | – | WP-62 (access control, synthetic-data guard, DEV-INSTANCE.md) |
| FOSS note: MIT does **not** exempt Art. 50 | Art. 2(12) AI Act | D | D | D | this part (WP-60) |
| Purpose: claimant-side, not authority-side | Annex III(5)(a) AI Act | A | A | A | WP-61 (self-assessment, purpose-drift lint), D-020 |
| AI-interaction notice to every natural person | Art. 50(1) AI Act | – | – | **A** | WP-64 |
| Machine-readable marking of all AI outputs | Art. 50(2) AI Act | – | – | **A** (deadline: **2026-12-02**, only if `provider` by then) | WP-65 |
| Disclosure for published text (public interest) | Art. 50(4) AI Act | – | – | – (not triggered: action documents are individual correspondence, not publication) | WP-65 (reasoning recorded in marker spec) |
| RDG single-case boundary (structural, pipeline-enforced) | § 2/§ 6/§ 8 RDG | – | – | A | WP-67, D-021 |
| GDPR: DPIA (Art. 35) + AVV chain (Art. 28) | GDPR | – (synthetic data only) | – (own data) | **A** (before the first real case) | WP-68 |
| Provider go/no-go gate | — (aggregate) | – | – | A (before first third-party use) | WP-69 |

**Quick answer in one sentence:** An instance in `dev` or `self` mode carries
no AI Act obligations and no GDPR/RDG triggers; an instance in `provider`
mode has the obligations marked **A** in the matrix active before the first
real third-party case may be processed — in particular Art. 50(1), Art. 50(2),
the RDG invariant, DPIA/AVV and the go/no-go gate.

### C.3 The Switch: DEPLOYMENT_MODE

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

**Implementation status:** The switch is implemented — `DEPLOYMENT_MODE` in
`app/core/config.py` (default `dev`, validated via `Literal`). In `dev` mode
the instance refuses to start without explicitly setting
`CITIZEN_SYNTHETIC_DATA_ONLY=true` (`app/services/dev_guard.py`) and rejects
document uploads lacking `X-Document-Tag: synthetic|goldset` with HTTP 403.
Hardening of the reachable instance is documented in
`devdocs/DEV-INSTANCE.md`.

### C.4 Classification in Detail

#### C.4.1 Providers and Deployers (Art. 3(3)/(4))

- **Provider** (Art. 3(3)): a person that develops an AI system, or has it
  developed, and places it on the market or puts it into service under its
  own name.
- **Deployer** (Art. 3(4)): a person using the system, other than in a
  personal non-professional activity.

In `dev`/`self` the author is neither: nothing is placed on the market and
nothing is put into service for third parties. In `provider` the author is
the provider. A deploying social-advice center is a **deployer** within
Art. 3(4) and — in data-protection terms — the **controller** within
Art. 4(7) GDPR.

#### C.4.2 Development Phase (Art. 2(8))

The AI Act does not apply to AI systems specifically developed and put into
service for the sole purpose of scientific research and development. The
`dev` mode is in this phase: reachable for testing, made available to no one.
For this classification to hold, the dev instance must satisfy three
conditions (runbook in `devdocs/DEV-INSTANCE.md`): (1) access by the author
only (VPN/mTLS or Basic Auth + IP allowlist), (2) synthetic data only
(startup assertion + ingest guard), (3) no indexing (`robots.txt`,
`X-Robots-Tag: noindex`) and a persistent development banner retrievable via
`GET /api/v1/meta/deployment-mode`, which clients must display.

#### C.4.3 FOSS Exemption (Art. 2(12)) — and the Art. 50 Carve-Back

Citizen is MIT-licensed. AI systems released under free and open-source
licences are exempt from most of the AI Act — **but Art. 50 (transparency
obligations) is expressly carved back in** and remains applicable. The licence
therefore changes nothing about the fact that the Art. 50 obligations apply in
`provider` mode (AI-interaction notice, machine-readable output marking). In
`dev`/`self` mode Art. 50 does not apply because there is **no provision to
third parties** — not because of the licence.

#### C.4.4 Self-Assessment: Not High-Risk (Annex III(5)(a))

**Result.** Citizen is **not a high-risk AI system** within the meaning of
Annex III(5)(a) AI Act — given the declared intended purpose (D-020) and the
safeguards against purpose drift documented in this section.

**Scope of the trigger.** Annex III(5)(a) covers AI systems used by public
authorities, or on their behalf, to **evaluate the benefit eligibility** of
natural persons for social benefits and services. The defining element is
authority-side use to decide eligibility.

**Declared intended purpose (D-020).** Citizen's intended purpose is
**claimant-side self-help and advisor assistance**: the system helps the data
subject or their advisors understand, review and respond to a Bescheid. It is
expressly **not** intended to be used by an authority, or on an authority's
behalf, to evaluate benefit eligibility.

**Why the trigger is not met.**

1. **No authority-side purpose:** Neither the product nor its documentation
   describes Citizen as an authority-side tool. The intended purpose is
   anchored in the README, Part A of this document, and the legal notice.
2. **Not a decision system:** Citizen produces legal information and building
   blocks requiring human adjudication (D-021); it does not decide benefit
   eligibility and is not provided for that purpose.
3. **Provision model:** Even in `provider` mode the software is made available
   to claimants and advice centers — not to authorities for eligibility
   evaluation.
4. **Classification by intended purpose:** The AI Act classifies by intended
   purpose. As long as the intended purpose remains claimant-side, the
   Annex III(5)(a) trigger is not met.

**Drift safeguards.** For this assessment to hold:

- **D-020** fixes the claimant-side intended purpose and prohibits
  authority-side descriptions in the documentation.
- **`scripts/check_purpose_drift.py`** (WP-61) scans the project's
  user-facing Markdown documents for authority-side phrasing (configurable
  deny-phrase list) and fails CI on any match. The lint is the technical
  enforcement of the intended purpose against drift.
- **Change management:** Changes to the intended purpose, target group or
  provision model require a version change of this document (section C.7) and
  a re-review of this self-assessment.

**Condition.** This assessment is conditional: it holds only for the declared
intended purpose. If Citizen is ever described as an authority-side tool or
provided to authorities for eligibility evaluation, the classification must be
re-assessed — the obligations for high-risk AI systems (Chapter III AI Act)
would apply.

### C.5 Deadlines and Triggering Events

| Event / deadline | Effect |
|---|---|
| **Provision to third parties** (`DEPLOYMENT_MODE=provider`) | Switches on the Art. 50 obligations as well as the GDPR and RDG requirements (see section C.2) |
| **2026-12-02** (end of the grace period for Art. 50(2)) | **Binding only if** `provider` applies by then: the machine-readable marking must be complete by that date. Otherwise it gates the later deployment. |
| **First real third-party case** | Processing only after: purpose guard green (WP-61), notice live (WP-64), marking live (WP-65), RDG invariant tested (WP-67), DPIA + AVV chain in place (WP-68), go/no-go gate signed (WP-69). |

### C.6 Adjacent Legal Regimes

#### C.6.1 GDPR

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

#### C.6.2 RDG (German Legal Services Act)

A system that examines one identified person's specific Bescheid sits near the
line of *Rechtsdienstleistung in konkreter fremder Angelegenheit* (§ 2 RDG).
The project position (D-021):

- Every output is **legal information plus building blocks** requiring human
  adjudication; no output is presented as a completed legal assessment of the
  individual case.
- Unadjudicated legal assertions appear in action documents as
  `[BITTE PRÜFEN]` placeholders — technically enforced, not merely declared
  (WP-67).
- For advice-center use, the § 6/§ 8 RDG frame (gratuitous legal services /
  recognized advice centers) is documented (WP-67).

### C.7 Validity and Change Management

- This part originates in Roadmap v2.0.0 (WP-60/WP-61) and is anchored in the
  decision ledger via decisions D-019, D-020 and D-022 (and, in its work
  package, D-021).
- Changes to the intended purpose, deployment form or target group require a
  review and a version change of this document (semantic versioning).
- Open legal questions that cannot be closed technically are collected in
  Roadmap v2.0.0 §8.

#### References

- `docs/roadmap-v2.0.0.md` — Phases P6–P8, obligation matrix (§5)
- `DECISIONS.md` — D-019, D-020, D-021, D-022
- `README.md` — section „Rechtlicher Status"
- `devdocs/DEV-INSTANCE.md` — dev-instance operations manual (Art. 2(8))
- `scripts/check_purpose_drift.py` — purpose-drift lint (WP-61)

---

## Change History

- **2.0.0 (2026-08-25):** Consolidation of the formerly standalone documents
  `DISCLAIMER_EN.md` (v1.1.0), `STATEMENT.md` (v1.0.0) and `COMPLIANCE-EN.md`
  (v1.1.0) into a single version (Part A statement, Part B legal notice,
  Part C compliance). Content aligned with the current implementation
  (API-only refactor D-025): B.12 acknowledgment mechanics adjusted to actual
  logging (version via `X-Disclaimer-Ack`, audit log per run; no checksum);
  active profile display via `GET /meta/active-profile`; implementation status
  of the `DEPLOYMENT_MODE` switch recorded as implemented incl. startup/ingest
  guards; UI references removed; reference to `AI-USAGE.md` (WP-63) marked as
  planned.
- **1.1.0 (2026-07-12/13):** Legal notice: versioning and change history
  introduced; gratuitous provision clarified; RDG clarification (§ 2);
  inference profiles/pseudonymization rewritten (§ 4); liability standards for
  gratuitous transfer (§ 6); app-side first-time confirmation (§ 12).
  Compliance: canonical classification (WP-60/WP-61) with obligation matrix,
  Annex III self-assessment and drift safeguards first published.
- **1.0.0 (2026-05-09 / July 2026):** Original versions of the legal notice
  (published at the time without version designation) and the project
  statement.
