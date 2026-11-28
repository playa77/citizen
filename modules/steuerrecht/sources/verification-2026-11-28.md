# WP-137 source verification — 2026-11-28

Inspected official consolidated Gesetze im Internet text. HTML SHA-256 metadata
is recorded in `snapshots-2026-11-28.json`; no private records, embeddings or
deployed corpus ingestion. One request in flight per publisher, >=2-second
pacing for the batch, no retries in the successful batch. Initial web access
timed out and sandbox DNS failed; approved host-network access succeeded. The
small later EGAO check used the same source and no concurrency.

| Source | Verified rule / identity |
|---|---|
| [EStG §32a](https://www.gesetze-im-internet.de/estg/__32a.html) | 2026 bands 12,348 / 17,799 / 69,878 / 277,825 euros; both income and computed tax rounded down to whole euros; §32a(5) splitting. |
| [EStG §9a](https://www.gesetze-im-internet.de/estg/__9a.html) | Employee 1,230 euros; qualifying §22 income 102 euros; cap by eligible income. No taxability calculation. |
| [EStG §20](https://www.gesetze-im-internet.de/estg/__20.html) | Abs.9 saver 1,000 / joint 2,000 euros capped by qualifying capital income after relevant loss computation. |
| [AO §108](https://www.gesetze-im-internet.de/ao_1977/__108.html) | Abs.3 includes Saturdays; roll to next workday. Abs.4/5 performance periods and authority appointments are distinct and unsupported. Corrects the old unimplemented-library comment. |
| [AO §122](https://www.gesetze-im-internet.de/ao_1977/__122.html) | Domestic post four days; lack/later receipt and proof disputes are exceptions. Electronic, foreign, public and formal delivery differ. |
| [AO §355](https://www.gesetze-im-internet.de/ao_1977/__355.html) | Ordinary objection one month after notification. |
| [AO §356](https://www.gesetze-im-internet.de/ao_1977/__356.html) | Defective/absent instruction one year with express statutory exceptions; force majeure and an instruction excluding objection need review. |
| [AO §149](https://www.gesetze-im-internet.de/ao_1977/__149.html) | Ordinary unadvised mandatory calendar-year return seven months after year end; advised and authority-requested regimes distinct. |
| [EGAO Art.97 §36](https://www.gesetze-im-internet.de/aoeg_1977/art_97__36.html) | Pandemic transition extensions concern historical years, not 2026. Referenced as verification evidence, not a new corpus source type. |
| [AO §361](https://www.gesetze-im-internet.de/ao_1977/__361.html) | Objection generally does not suspend collection; separate suspension/annulment decision and possible security. |
| [AO §172](https://www.gesetze-im-internet.de/ao_1977/__172.html) | Qualified amendment request in the supported ordinary regime; favourable request generally before objection deadline. No replacement of objection. |
| [StBerG §2](https://www.gesetze-im-internet.de/stberg/__2.html) | Assistance for others is reserved; module supports own-matter preparation only. |
| [SolZG](https://www.gesetze-im-internet.de/solzg_1995/index.html), [FGO](https://www.gesetze-im-internet.de/fgo/index.html) | Official federal corpus identities verified; no Soli calculation or financial-court deadline automation claimed. |

Tariff coefficients are stored as exact decimal strings in proposed parameters.
Filing date: 2026 year end + seven months is Saturday 2027-07-31; §108(3)
ordinary workday date is Monday 2027-08-02, subject to explicit local-calendar
confirmation and future legal changes. This narrow precomputed date does not
provide a general filing-date engine or automatic eligibility determination.

The parser/citation tests use synthetic fixtures, not a claim of successful
deployment population or complete consolidated-law ingestion. Parameters/copy
remain proposed/draft and require deferred human review.
