# Steuerrecht — experimental own-matter preparation

Version 0.1.0, source inspection 2026-11-28. Core 3.12.0 / module API 3.10.
Human legal/language review and promotion remain pending under D-071.
No assistance for others or advice-center mode; metadata is not authenticated
role enforcement. No gettsim/AGPL embedding, filing, ingestion or live inference.

## Coverage

| Check | Supported | Limits |
|---|---|---|
| AO objection | Current, confirmed ordinary domestic postal assessment; dispatch from 2025 | Four days, §108 workday rollover; early receipt does not shorten presumption. Later/disputed/nonreceipt, electronic/formal/foreign modes and special regimes require individual review. |
| Instruction defects | Confirmed absent/incorrect instruction | One year only with §356 exceptions expressly excluded; no general extension promise. |
| Income-tax tariff | Tax year 2026, basic or confirmed §32a(5) joint splitting | Confirmed taxable income in cents, statutory euro rounding; no gross conversion, §32a(6), special tariffs, progression, Soli, church tax, deductions/credits or complete assessment. |
| Allowances | 2026 employee €1,230; qualifying §22 pension income €102; saver €1,000 / confirmed joint €2,000 | Capped by qualified income; no higher-expense claim assessment, pension taxation computation or §19 pension allowance. Saver input already reflects qualified loss computation. |
| Assessment comparison | Same-basis 2026 cent amounts | Assessed minus declared; no finding of illegality, entitlement or refund. |
| Filing | Mandatory, unadvised calendar-year 2026 return | Nominal 2027-07-31, rolled to 2027-08-02. Explicit state, no extra local holiday, current law and no individual/special/transition regime required. Advised/voluntary returns unsupported. Not a payment deadline. |
| Drafts | Einspruch, Aussetzung, schlichte Änderung | Unconfirmed assertions retain `[BITTE PRÜFEN]`; request alone does not suspend payment or replace other remedies. |

## Explicit calculator input

The LLM-driven path accepts a single `CITIZEN_TAX_FACTS:` JSON object in the
source. Facts must satisfy the calculator allowlist and public intake schema;
the model cannot establish confirmation flags. Direct pure calls similarly
require explicit qualifications and valid `tax_rules` parameters. This does not
independently verify the person's legal assessment. The explanation summary
omits financial amounts and identifiers. No tax IDs/bank details are needed.

See [source verification](sources/verification-2026-11-28.md),
[parameters](parameters/tax.yaml), [change record](CHANGELOG.md) and
[D-079](../../docs/decisions/D-079-wp137-tax-implementation.md).
