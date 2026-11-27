# WP-132 primary-source verification

Verified on 2026-11-27. Status: experimental; legal/human review deferred under
D-071. This is evidence for implementation, not a legal opinion or deployment
corpus ingestion. Sources below are official federal statutory publications or
judgments unless explicitly identified otherwise. Retrieval establishes the
published text seen on this date, not individualized applicability or future
legal stability. No live inference, embeddings or credentials were used.

## Collection limits and retrieval evidence

Collection budget: at most 24 source operations, one in flight, at least two
seconds between repeated requests to the same source; unrelated hosts need not
wait. 20 operations were used (including failed opens and a failed find).
The first web call inadvertently grouped three opens; subsequent substantive
collection was serial. The web provider's internal fetch/retry timing is opaque;
no claim is made that its internal requests met the stated pacing. Failed direct
opens of §38 SGB III, §5 BUrlG and §188 BGB were replaced by official indexed
text or a consolidated official PDF. The §159 BA PDF open/find timed out;
only its indexed official excerpt was obtained. No persistent-error retry loop.

## Dismissal and severance

[Official KSchG consolidated PDF](https://www.gesetze-im-internet.de/kschg/KSchG.pdf)
(retrieved; last amendment stated: 14 June 2021): §4 requires filing in the
Arbeitsgericht within three weeks of receipt of written dismissal, including
other invalidity grounds. Required administrative consent changes the start to
notification of the authority's decision to the employee; do not resolve that
special case with ordinary receipt alone. §5 permits late admission on application
only under qualified conditions, including sufficient diligence; application
must accompany/refer to the action and substantiate facts. Its text specifies
two weeks after removal of the obstacle and an outer six-month limit following
the missed deadline. These are review issues, not automatic extensions. §13
preserves the filing requirement for extraordinary dismissal. §10(3) defines
monthly earnings by regular working time in the termination month, including
money and benefits in kind. Exact quote (§4): “innerhalb von drei Wochen nach
Zugang der schriftlichen Kündigung”.

[Official §1a KSchG](https://www.gesetze-im-internet.de/kschg/__1a.html)
(retrieved): statutory severance requires operational dismissal, the specific
employer notice in the dismissal declaration, and no timely dismissal action;
claim arises at expiry of the notice period. Formula: 0.5 monthly earnings per
employment year, with §10(3)'s earnings definition. Only a residual employment
period **greater than six months** rounds up to another year; exactly six months
does not. Quote: “mehr als sechs Monaten”. There is no universal entitlement
from termination alone. An estimate must never recommend allowing the action
period to expire. Year/month arithmetic must be calendar based rather than a
365-day approximation; leap dates need explicit tests.

## Ordinary notice

[Official §622 BGB](https://www.gesetze-im-internet.de/bgb/__622.html)
(retrieved): ordinary baseline is four weeks (28 days), ending on the 15th or
month end. Employer notice after completed employment of 2/5/8/10/12/15/20
years is respectively 1/2/3/4/5/6/7 calendar months, ending at month end.
Agreed probation permits two weeks for at most the first six months. Collective
agreements may deviate; individual-contract exceptions and longer periods need
specific evidence. An employee's agreed notice cannot exceed the employer's.
Quote: “vier Wochen zum Fünfzehnten oder zum Ende eines Kalendermonats”.
Do not treat four weeks as one month or apply employer seniority increments to
employee resignation automatically. Unsupported tariff, contractual or special
statutory regimes must produce a review/unsupported result.

## Early jobseeker registration (§38 SGB III)

[Official §38 SGB III](https://www.gesetze-im-internet.de/sgb_3/__38.html)
(direct open failed; official indexed text retrieved): report no later than three
months before employment/training ends. If knowledge of the **termination date**
comes less than three months before that date, report within three days after
knowledge. Exactly three months belongs to the ordinary branch. Duty persists
while continuation is litigated or promised; in-company vocational training is
excluded. Quote: “innerhalb von drei Tagen nach Kenntnis des Beendigungszeitpunktes”.
Knowledge and receipt are distinct confirmed facts; never substitute letter date.
[BA current public instructions](https://www.arbeitsagentur.de/arbeitslos-arbeit-finden/arbeitslosengeld/ihre-schritte-wenn-sie-arbeitslos-werden/wie-sie-sich-arbeitsuchend-melden)
(indexed) confirm both periods, recommend immediate reporting and distinguish
jobseeker from unemployment registration.

[Official §26 SGB X](https://www.gesetze-im-internet.de/sgb_10/__26.html)
(retrieved) applies §§187–193 BGB and moves a deadline ending Saturday, Sunday
or statutory holiday to the next working day. Quote: “mit dem Ablauf des
nächstfolgenden Werktages”. [Official §188 BGB](https://www.gesetze-im-internet.de/bgb/__188.html)
(direct open failed; official indexed text retrieved) supplies corresponding
week/month dates and month-end clamping when the numbered day is absent.
A conservative short-branch calculation excludes the knowledge day, adds three
calendar days and applies the end rollover. This does **not** establish that
intervening closed-agency days can never extend the actual individual period.

Unresolved qualification: the BA-authored April 2022 *Leitfaden zur Einleitung
frühzeitiger Integrationsaktivitäten*, pp.11–12, is indexed on a
[third-party mirror](https://fragdenstaat.de/dokumente/277977-leitfaden-integrationsaktivitaeten-sgb3/?page=6).
Its excerpts describe three-month subtraction by corresponding day, month-end
clamping and forward end rollover, and exclude days without agency service
readiness/objective hindrance from the short period. Its present operative
status was not independently verified. The official
[BA §159 instructions](https://www.arbeitsagentur.de/datei/fw-sgb-iii-159_ba034410.pdf)
(indexed excerpt, 12/2023; PDF fetch failed) refer to that guide but did not
resolve the calendar distinction. Therefore display a conservative reporting
reminder, do not decide lateness/Sperrzeit or promise individualized extensions.
Agency closures, illness and other obstacles require review. A uniform three
business-day assertion is also unsupported by the currently retrieved statute.

## Leave and compensation

[Official BUrlG PDF](https://www.gesetze-im-internet.de/burlg/BUrlG.pdf)
(retrieved; last amendment stated: 20 April 2013), §§3–7/11: minimum 24 working
days on the statutory six-day basis; full entitlement first after six months.
§5 awards one twelfth per full employment month only in its enumerated
partial-entitlement cases, including departure in the first half-year after
waiting time. Do not automatically prorate second-half departure after waiting
time. In §5 partial leave, fractions at least 0.5 round up; smaller fractions
are not ordered to round down. §6 prevents duplicate current-year entitlement.
§7(4) permits compensation where termination prevents granting leave. §11 uses
average earnings in the preceding 13 weeks, excluding extra overtime pay;
permanent raises and involuntary reductions require adjustments. Statutory
carryover text is not a complete modern forfeiture test; employer cooperation,
illness and case law require review. Quote (§5): “mindestens einen halben Tag”.
For a fixed five-day week, 24 × 5/6 = 20 days is the implementation conversion,
not an additional statutory entitlement. Compensation must preserve fractions
and exact arithmetic until final money rounding; unsupported pay schedules,
special protection and tariff regimes require review.

[Official BAG judgment 8 May 2018, 9 AZR 578/17](https://www.bundesarbeitsgericht.de/entscheidung/9-azr-578-17/),
paragraphs 11–13 (retrieved), rejects rounding without a separate legal rule;
§5(2) is a limited partial-leave rule, not a universal rounding license. It
upheld the employee's 0.15-day residual claim in that dispute. Quote: “ohne eine
gesonderte Rundungsvorschrift”. Do not use this older judgment's factual
forfeiture discussion as a complete statement of present forfeiture law.

## Minimum wage and exceptions

[Official MiLoV4 §1](https://www.gesetze-im-internet.de/milov4/__1.html)
and [official MiLoV5 §1](https://www.gesetze-im-internet.de/milov5/__1.html)
(retrieved): general gross hourly floors are EUR12.82 from 2025-01-01,
EUR13.90 from 2026-01-01 and EUR14.60 from 2027-01-01. The 2027 rate is enacted,
not merely a commission proposal. [BMAS statutory wage chronology](https://www.bmas.de/DE/Arbeit/Arbeitsrecht/Mindestlohn/Glossar/G/Gesetzlicher-Mindestlohn.html)
(indexed) identifies MiLoV4 dated 24 November 2023 (BGBl.2023 I Nr.321), and
MiLoV5 dated 7 November 2025 (BGBl.2025 I Nr.268). Apply rates to work dates,
split periods crossing a change, and do not back-apply the current rate.
2027 is prospective as of this verification date; later periods need fresh
coverage. Sector-specific higher floors are not calculated here.

[Official MiLoG §22](https://www.gesetze-im-internet.de/milog/__22.html)
(retrieved): applicability exceptions include minors without completed vocational
training; vocational trainees and honorary activity; the first six employment
months after immediately preceding long-term unemployment; mandatory internships;
up-to-three-month orientation internships; qualifying up-to-three-month
education-accompanying internships without an earlier such internship with the
same trainer; entry qualification and vocational preparation specified by law.
Actual internship circumstances control, not its label. Unknown exception facts
must block an unconditional statutory comparison. [BMAS overview, 26 January
2026](https://www.bmas.de/DE/Arbeit/Arbeitsrecht/Mindestlohn/Informationen-zum-Mindestlohn/informationen-zum-mindestlohn-deutsch.html)
(indexed) confirms coverage also for minijobs, seasonal/foreign employees working
in Germany, and remuneration per actual hour. This evidence does not establish
which disputed allowances count as remuneration; require confirmed eligible
pay and hours and refuse unsupported arrangements.

## Review gates

All derived examples are synthetic. Runtime parameter files must identify their
own covered dates and qualifications. This document verifies source text only:
it does not prove corpus ingestion, calculator behavior, deadline implementation,
legal quality or completed human review. KSchG pregnancy/consent exceptions,
leave forfeiture, disputed remuneration and individual agency hindrances remain
qualified review topics. No source here authorizes automatic sending or signing.


## Final adapter identity check

The current [MuSchG consolidated text](https://www.gesetze-im-internet.de/muschg_2018/BJNR122810017.html)
and [section 17](https://www.gesetze-im-internet.de/muschg_2018/__17.html) were verified
from official indexed text during final integration. A direct directory open
failed once; one subsequent targeted indexed search established the current
`muschg_2018` directory. The stable runtime source key remains `muschg`; it must
not be used as the directory slug. This adds two operations to the collection
record (22 total, within the original 24-operation budget); no ingestion occurred.
