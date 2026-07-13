# Legal Notice and Disclaimer

**Version:** 1.1.0

**Date:** 2026-07-13

**Supersedes:** Version of 2026-05-09 (retroactively designated as Version 1.0.0)

**Author:** www.github.com/playa77

**Repository:** https://github.com/playa77/citizen

This document contains legal notices and disclaimers. It does not replace or
modify the applicable open-source license terms unless expressly stated.

This software is provided under the MIT License and **gratuitously**. By
providing, accessing, or using it, no fee, exchange, or service relationship
is created.

To the extent this document contains contractual terms, they apply only to
the maximum extent permitted by applicable mandatory law.

Changes to this document follow semantic versioning; the change history is at
the end of this document.

---

## 1. Nature of the Software

This repository contains personal, bespoke software developed primarily for the
author's own use, documentation, experimentation, and personal reference.

The software has not been designed, tested, audited, certified, or approved for
production use, commercial use, public deployment, safety-critical systems,
security-critical systems, medical systems, financial systems, legal practice,
or professional legal advice, or any other environment where failure,
malfunction, data loss, incorrect outputs, or security issues could cause harm.

Public availability of this repository does not constitute a product offering,
professional service, legal service, recommendation, warranty, or
representation that the software is suitable for any particular purpose.

## 2. No Legal Advice

This software is a technical tool for informational, educational,
experimental, and personal reference purposes only.

It does not constitute legal advice, professional consultation, legal
representation, or a substitute for advice from a qualified lawyer or other
qualified professional.

The author does not act in specific third-party matters within the meaning of
§ 2 (1) of the German Legal Services Act (Rechtsdienstleistungsgesetz, RDG).
The software operates schematically according to predetermined rules, procedures,
and verification steps; no case-specific legal review by the author takes place.
Users who apply the software to their own documents and their own affairs handle
their own legal matters (self-assistance). Use of the software in the context of
advising or assisting third parties is permitted only to those entities and persons
who are authorized to do so under the RDG or other provisions; responsibility for
the existence of such authorization and for the advice itself rests solely with
those entities and persons.

No attorney-client relationship, mandate, fiduciary relationship, advisory
relationship, or other professional legal relationship is formed by accessing,
installing, running, or using this software.

You must not rely on this software as the sole basis for legal decisions,
filings, applications, objections, appeals, communications with authorities,
contractual decisions, litigation strategy, or any other legally relevant
action.

Always consult qualified legal counsel before taking or refraining from any
action with legal consequences.

## 3. AI-Generated Content and Accuracy

Outputs may be generated using artificial intelligence, large language models,
automated retrieval systems, ranking systems, citation systems, or other
automated processes.

Even where the software attempts to use evidence-binding, retrieval
augmentation, source references, citation tracking, or similar mechanisms,
outputs may be inaccurate, incomplete, misleading, outdated, hallucinated, or
based on incorrect interpretation of statutes, regulations, administrative
guidance, case law, contracts, policies, or other materials.

The author does not warrant or represent that any output is correct, complete,
current, legally valid, admissible, reliable, or suitable for any specific use.

You are solely responsible for independently verifying all outputs against
official, current, and authoritative sources before using them. This includes,
where applicable, checking original statutes, regulations, administrative
materials, court decisions, official publications, deadlines, procedural
requirements, and professional legal advice.

## 4. Data Processing, Data Protection, and Inference Profiles

The software stores data locally. To the extent the software uses external
services for processing (in particular language model and embedding services),
this is done exclusively through configurable, versioned **inference profiles**.
The currently active profile is displayed in the application and indicated in
generated documents.

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
  Pseudonymized input data may be transmitted to external providers, including
  to servers outside your country or legal jurisdiction, including regions with
  different data protection laws and data protection standards.
- **on-prem** (if configured): no external transmission.

Pseudonymization covers direct identifiers according to the documented rule set.
Residual risks — in particular, potential identifiability from the remaining
case context as well as misdetection of individual items — cannot be ruled out.
Pseudonymized data remain personal data within the meaning of the GDPR.

The author does not control third-party providers and does not — even if a data
processing agreement exists — warrant or guarantee their security measures,
availability, data storage, deletion practices, use for training purposes,
confidentiality, regulatory compliance, or compliance with the GDPR or other
data protection laws. The selection, vetting, and contractual engagement of
external providers is the responsibility of whoever operates the software.

Anyone who applies the software to **their own** documents and data as a data
subject decides on this under their own responsibility and consents under the
respectively active profile. Anyone who processes data of **third parties**
with the software (in particular advisory centers and other organizations) is
themselves the controller within the meaning of the GDPR and is solely
responsible for determining and complying with all obligations under applicable
data protection law, confidentiality law (in particular the German social data
protection provisions of § 35 SGB I, §§ 67 ff. SGB X), professional law,
consumer protection law, and information security law — including the legal
basis, information of data subjects, required consent, data processing
agreements, technical and organizational measures, records of processing
activities, and, where required, a data protection impact assessment.

Special categories of personal data, confidential information, privileged
information, trade secrets, client data, and other sensitive information may
only be entered or processed if the above prerequisites are met.

This disclaimer is not a privacy policy.

You are solely responsible for any data you input, process, transmit, store, or
disclose using the software.

## 5. No Warranty

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

## 6. Limitation of Liability

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
- unauthorized access to, use of, or alteration of your transmissions, content,
  prompts, documents, or data;
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

## 7. User Responsibility and Assumption of Risk

You are solely responsible for evaluating whether the software and its outputs
are suitable for your intended use.

If you access, clone, download, install, build, run, modify, deploy, interact
with, or otherwise use the software, you do so at your own risk.

You are solely responsible for all decisions, filings, applications,
objections, appeals, communications, submissions, legal actions, administrative
actions, business decisions, or other actions taken or omitted based on outputs
from this software.

You are responsible for taking appropriate precautions, including independent
legal review, professional advice, code review, security review, testing,
backups, verification of sources, checking deadlines, checking procedural
requirements, and compliance with applicable laws and regulations.

## 8. No Support or Maintenance

The author has no obligation to provide support, maintenance, updates, bug
fixes, security fixes, documentation, responses to issues, responses to pull
requests, or any other assistance.

The publication of this repository does not create any service relationship,
consulting relationship, fiduciary relationship, employment relationship,
partnership, professional relationship, or other special relationship between
the author and any user.

## 9. Third-Party Components and Services

This repository may contain, reference, call, or depend on third-party
software, libraries, models, APIs, services, tools, data, or documentation.

Third-party components and services are provided under their own terms,
licenses, policies, and privacy practices. You are solely responsible for
reviewing and complying with those terms.

The author is not responsible for third-party components or services and makes
no warranty or representation regarding them.

## 10. Governing Law and Jurisdiction

To the extent legally permissible, this disclaimer shall be governed by the
laws of the Federal Republic of Germany, excluding the United Nations
Convention on Contracts for the International Sale of Goods.

If you are a consumer habitually resident in another country, including a
member state of the European Union or the United States of America, this choice
of law does not deprive you of any mandatory consumer protection rights or
other mandatory rights under the laws of your country of habitual residence.

To the extent legally permissible, if the user is a merchant, a legal entity
under public law, or a special fund under public law, the courts at the
author's place of residence or registered office in Germany shall have
jurisdiction. Mandatory statutory venues remain unaffected.

## 11. Severability

If any provision of this disclaimer is held to be invalid, unlawful, or
unenforceable, the remaining provisions shall remain in effect to the maximum
extent permitted by law.

The invalid, unlawful, or unenforceable provision shall be interpreted,
limited, or replaced to the extent necessary to make it valid and enforceable
while preserving its intended purpose as closely as legally possible.

## 12. Acknowledgment

By accessing, installing, running, interacting with, or using this software,
you confirm that you have read and understood this disclaimer and that you use
the software at your own risk.

The application requires an express confirmation of acknowledgment upon first
start and after material changes to this document, and records locally the
confirmed version (version number and checksum of the document, timestamp,
application version). The version displayed and confirmed in the application at
any given time is authoritative. Documents and reports generated by the
software indicate the underlying version in the footer.

If you do not agree with this disclaimer, do not use the software.

---

## Change History

- **1.1.0 (2026-07-13):** Versioning and change history introduced.
  Preamble: gratuitous nature of the provision expressly clarified.
  § 2: RDG clarification added (no activity in specific third-party matters,
  schematic mode of operation, self-assistance character, use in advising third
  parties only by authorized persons). § 4: completely rewritten — description
  of versioned inference profiles (eu-avv / extern-openrouter / on-prem),
  technically enforced pseudonymization and its limits; delimitation of
  responsibility between self-assistance use of own data and processing of
  third-party data (GDPR controller, social data protection provisions).
  § 6: reference to legal standards for gratuitous transfers added.
  § 12: app-side first-time confirmation with recorded document version added.
  §§ 3, 5, 7–11 unchanged.
- **1.0.0 (2026-05-09):** Original version (published at the time without
  version designation).
