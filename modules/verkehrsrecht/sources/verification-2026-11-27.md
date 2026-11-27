# Primary-source verification — 2026-11-27

Status: draft; human review pending under D-071. Official current consolidated HTML fetched with one request in flight, two-second spacing, 20-second timeout, no automatic retries. Sandbox DNS denial was followed by one approved collector execution. No embeddings or deployment ingestion.

## OWIG

- Official source: [owig](https://www.gesetze-im-internet.de/owig_1968/BJNR004810968.html)
- SHA-256: `b7b61197686978d7f885ab4f51e706328206c66e97543b50891d5810b42a3b79`
- Verified anchors: §31, §32, §33, §46, §49, §55, §66, §67, §111

## STVG

- Official source: [stvg](https://www.gesetze-im-internet.de/stvg/BJNR004370909.html)
- SHA-256: `aac94b0eb64562a014da580a246cc471afa9e5031bb2f01bf47e70c6957016db`
- Verified anchors: §4, §25, §26, §29

Current §26(3): standard §24(1) traffic offences use six months; vehicle-type-approval and §24(2) exceptions are excluded. Current §25(2): effectiveness upon custody/endorsement, at latest one month after finality. Four-month order is now §25(3) no.1, not former §25(2a). §25(6) separates duration start. Snapshot does not prove historical applicability.

## STPO

- Official source: [stpo](https://www.gesetze-im-internet.de/stpo/BJNR006290950.html)
- SHA-256: `fe6b5d7efda4e31e04ecef502f3edd953ef99982cf912d5b50e4667436d0e266`
- Verified anchors: §42, §43, §52, §55, §136

## BKATV

- Official source: [bkatv](https://www.gesetze-im-internet.de/bkatv_2013/BJNR049800013.html)
- SHA-256: `a66daf0505b4b2eb933fc60e7e732106be1e1df3a11d51e5061560812f6c8ffd`
- Verified anchors: §1, §3, §4

Verified Anlage no.11.3, Anhang Tabelle 1c: 10 speed bands, each inside/outside built-up areas; amounts and regular ban months. §1 ordinary circumstances, §3 aggravation/intent and §4(2) repeat offences require qualification. Full annex ingestion is unsupported.

## FEV

- Official source: [fev](https://www.gesetze-im-internet.de/fev_2010/BJNR198000010.html)
- SHA-256: `fe894e9b78d67026007489f04f76be8cb73f404c0b634f83fcaa3c9bdd988b79`
- Verified anchors: annex identities and scope

Verified Anlage13 nos.2.2.3 and 3.2.2: speed-table point classifications. This is selected parameter coverage only, not complete annex retrieval.

## STVO

- Official source: [stvo](https://www.gesetze-im-internet.de/stvo_2013/BJNR036710013.html)
- SHA-256: `1d3e9eaebaac6ea1adc99b00dc13db7e72a787a48a2c152eb860dae083028047`
- Verified anchors: annex identities and scope

## Date semantics and limits

Objection uses §67 OWiG with §43(1)–(2) StPO (weeks, not §42 day periods); actual domestic service and confirmed statewide/local calendar. Substantive limitation and register periods count the event day; no procedural rollover. Missing anniversary day uses the target month end. Ban effectiveness caps use the corresponding calendar date without procedural extension. Record retention and one-year overlap are distinct; no current-score or permission-to-drive determination.

## Deferred evidence

No historical consolidation, case-law completeness, live inference, human promotion or deployed retrieval is established. Raw publisher HTML was inspected locally for the six sources. The application scraper was checked offline against those cached snapshots; runtime annex/table coverage remains explicitly partial.

## Parser snapshot check

Offline parsing of the cached official HTML produced 404 OWiG, 465 StVG, 275 StVO, 22 BKatV, 350 FeV and 1,754 StPO paragraph chunks with preserved law/source identity. Annexes/tables remain excluded. Review regression clarifications: §33(1) no.1 can interrupt only once; driving-ban commencement is never an expiry field; deletion is after the inclusive overlap end, including leap-year boundaries.
