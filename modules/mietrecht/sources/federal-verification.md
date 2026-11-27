# Federal anchors checked for WP-131

Checked through official indexed/HTML sources on 2026-11-26/27. Human legal
review is pending. These notes describe source checks, not corpus ingestion or
full historical applicability. Snapshot parameter validity begins 2026-11-26.

| Anchor | Official source | Implemented qualified semantics |
|---|---|---|
| §558 BGB | https://www.gesetze-im-internet.de/bgb/__558.html | Three-year baseline, 20% federal / designated15% cap, comparison rent; 15-month stability, one-year request interval and exceptions need confirmation. No unverified geographic default. |
| §556d BGB | https://www.gesetze-im-internet.de/bgb/__556d.html | Designated area, 10% over confirmed comparison rent at tenancy start; regulation expiry no later than2029-12-31. |
| §§556e/f BGB | https://www.gesetze-im-internet.de/bgb/__556e.html ; https://www.gesetze-im-internet.juris.de/bgb/__556f.html | Prior rent/modernization and first-use/new-building exceptions require explicit assessment. Exceptions block the simple ceiling instead of guessed alternative amounts. |
| §551 BGB | https://www.gesetze-im-internet.de/bgb/__551.html | Three net monthly rents, three installments for cash security; no reimbursement/due-date finding. |
| §558b BGB | https://www.gesetze-im-internet.de/bgb/__558b.html | Consent window ends after the second calendar month following actual receipt. No automatic consent. |
| §556 BGB | https://www.gesetze-im-internet.de/bgb/__556.html | Objections by end of twelfth month after receipt; late/non-attributable exception remains for individual review. |
| §574b BGB | https://www.gesetze-im-internet.de/bgb/__574b.html | Two months backwards from tenancy end, conditional on timely rights notice; no forward holiday rollover. Missing notice can allow later objection. |
| §569 BGB | https://www.gesetze-im-internet.de/bgb/__569.html | Two months after confirmed pendency for qualified arrears cure; prior qualifying cure within two years excludes the simple rule. No automatic cure of an ordinary termination. |
| §573c BGB | https://www.gesetze-im-internet.de/bgb/__573c.html | Third Werktag cutoff, end of the month after next; landlord extensions after five/eight years. |
| HeizkostenV §7 | https://www.gesetze-im-internet.de/heizkostenv/__7.html | 50–70% consumption share; mandatory70% and exceptions require confirmation. Arithmetic only. |

§573c Saturday counting was checked against BGH VIII ZR206/04, 27April2005:
https://juris.bundesgerichtshof.de/cgi-bin/rechtsprechung/document.py?Art=pm&Blank=1&Datum=2005-4&Gericht=bgh&file=dokument.pdf&linked=urt&nr=32907

The last-day Saturday extension is also stated in the ministry's tenant guide:
https://www.bmjv.de/SharedDocs/Publikationen/DE/Broschueren/Mietrecht.pdf?__blob=publicationFile&v=5

Statewide holidays were checked against the Bundesbank's public2026 calendar:
https://www.bundesbank.de/resource/blob/749314/edbf269e7e236ff9dcf3e95dab122a0b/472B63F073F071307366337C94F8C870/feiertage-in-deutschland-1-data.pdf

Local holidays require explicit confirmation; Gregorian Easter avoids reusing
another year's movable holidays. The exceptional Berlin holiday on2025-05-08
is recorded in the Bundesbank's holiday memorandum:
https://www.bundesbank.de/resource/blob/671010/004a37865a3c96af7ddc08e057c3833d/472B63F073F071307366337C94F8C870/zv-merkblatt-feiertage-data.pdf

Direct shell collection failed with transport URLError for all eight attempted
URLs (no retries/download artifacts). Official web views supplied the checks
above; §556f was available through the official juris alias. BetrKV §1 direct
fetch timed out and its full text was not captured in this session. The module
therefore requires independent confirmation that supplied costs are allocable;
it does not implement a full cost-category classifier or mark this verification
complete. Source terms/ordinance review remains under OQ-7 and deferred D-071.
