# WP-136 statutory verification — 2026-11-27

Public primary-source HTML was retrieved from Gesetze im Internet with one
request in flight, >=2 seconds between requests and a 25-second request timeout.
The initial sandbox DNS failure was followed by an authorized network run;
there were no publisher-error retries. Retrieval stopped after the bounded
verification batch. No inference, embeddings or deployment ingestion occurred.
The adjacent JSON records snapshot SHA-256 hashes and public URLs; original
snapshots were inspected locally under /tmp, not bundled as a second corpus.

## Source identities

| Source type | Canonical law | Official index |
|---|---|---|
| aufenthg | AufenthG | https://www.gesetze-im-internet.de/aufenthg_2004/ |
| asylg | AsylG | https://www.gesetze-im-internet.de/asylvfg_1992/ |
| aufenthv | AufenthV | https://www.gesetze-im-internet.de/aufenthv/ |
| beschv | BeschV | https://www.gesetze-im-internet.de/beschv_2013/ |
| freizuegg_eu | FreizügG/EU | https://www.gesetze-im-internet.de/freiz_gg_eu_2004/ |
| stag | StAG | https://www.gesetze-im-internet.de/stag/ |
| vwgo | VwGO | https://www.gesetze-im-internet.de/vwgo/ |

All seven indices were inspected for identity. Focused operative provisions
below were retrieved and inspected. This is not a claim of complete paragraph,
annex, EU-law or state-law coverage or actual deployment corpus population.

## Operative findings and implementation limits

- [§74 AsylG](https://www.gesetze-im-internet.de/asylvfg_1992/__74.html):
  current regular lawsuit period two weeks; qualified weekly regimes include
  §34a and Article 67(7)(a) of Regulation (EU) 2024/1348. The current defective
  remedy-notice provision references three months, not a blanket VwGO year.
  No replacement period is automatically calculated.
- [§36 AsylG](https://www.gesetze-im-internet.de/asylvfg_1992/__36.html):
  current interim application period is one week in paragraph 2. The roadmap's
  older paragraph-3 shorthand is superseded for this verified current regime.
  [§34a(3)](https://www.gesetze-im-internet.de/asylvfg_1992/__34a.html)
  separately regulates interim applications for transfer orders. Both require
  qualified applicability; lawsuit and interim relief are separate items.
- [§87e AsylG](https://www.gesetze-im-internet.de/asylvfg_1992/__87e.html):
  transition refers to Article 79(3) of Regulation (EU) 2024/1348. The module
  does not infer this EU-law classification from a date or generic label.
  Old-law, transition, airport/border and unidentified regimes require immediate
  individual review. No unverified EU procedural branch is encoded.
- [§§57](https://www.gesetze-im-internet.de/vwgo/__57.html),
  [70](https://www.gesetze-im-internet.de/vwgo/__70.html),
  [73](https://www.gesetze-im-internet.de/vwgo/__73.html),
  [74](https://www.gesetze-im-internet.de/vwgo/__74.html),
  [58 VwGO](https://www.gesetze-im-internet.de/vwgo/__58.html),
  [§222 ZPO](https://www.gesetze-im-internet.de/zpo/__222.html),
  [§187](https://www.gesetze-im-internet.de/bgb/__187.html) and
  [§188 BGB](https://www.gesetze-im-internet.de/bgb/__188.html): ordinary
  month/two-week/week mechanics, explicit service/notification qualifications
  and current civil calendar. Only confirmed domestic formal service of the
  relevant decision/notification is supported. No postal fiction is assumed.
  State objection rules are not verified: all sixteen states explicitly remain
  unavailable for automatic selection in state-objection-coverage.yaml.
- [§81(4) AufenthG](https://www.gesetze-im-internet.de/aufenthg_2004/__81.html):
  compare proven application receipt with title expiry only under confirmed
  applicability, non-Schengen-visa and no-decision assumptions. Receipt on the
  last valid day is within that day; no weekend extension of title validity.
  [§51](https://www.gesetze-im-internet.de/aufenthg_2004/__51.html) has other
  extinction grounds; arithmetic does not establish continued legal status,
  work permission, travel permission or protection against removal.
- [§10 StAG](https://www.gesetze-im-internet.de/stag/__10.html): standard
  period is five years; paragraph 3 has been removed. Calendar anniversary
  arithmetic only, not an eligibility test or guaranteed earliest filing date.
  [§12b](https://www.gesetze-im-internet.de/stag/__12b.html) interruption/credit
  rules and §40a transition are excluded pending individual confirmation.
- [§2(3) AufenthG](https://www.gesetze-im-internet.de/aufenthg_2004/__2.html):
  livelihood includes adequate health insurance; exceptions/public-fund and
  special education regimes differ. Only arithmetic on explicitly confirmed
  income/need/insurance inputs is provided. No flat livelihood threshold,
  inferred social-law parameter or eligibility verdict is bundled.

Parameters are proposed and deliberately valid only from verification date
through 2026-12-31; no historical/future availability is claimed. Current
procedural-regime confirmation remains mandatory for every deadline. Human
legal/language review, live evaluation, deployment ingestion and P12 GUI/RTL
acceptance remain pending.
