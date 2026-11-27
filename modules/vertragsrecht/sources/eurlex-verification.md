# EUR-Lex verification — 2026-11-27

WP-133 / D-075. Experimental source coverage; human legal review remains deferred.

Official original act: [CELEX 32004R0261, German HTML](https://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=CELEX:32004R0261:DE:HTML), OJ L 46, 17 February 2004, pp. 1–8. Article 19 establishes applicability from 17 February 2005. The adapter labels this original act by that date; this does not establish consolidated-law or subsequent case-law coverage.

The official rendered text was inspected on 27 November 2026: distinct article headings 1–19; paragraph numbers and lettered lists. Article 3 qualifies geographical, booking/check-in and fare coverage. Article 5 separates cancellation notice/rerouting exceptions and extraordinary circumstances. Article 7 distinguishes distance categories, intra-community flights, qualified alternate-flight reductions and great-circle distance. A distance band alone does not establish entitlement. Article 6's assistance thresholds are not an automatic compensation entitlement.

Access evidence: modern `/legal-content/DE/TXT/HTML/` and `/TXT/` responses presented a JavaScript robot challenge. The official legacy endpoint returned readable text through the web reader; direct HTTP to that endpoint returned 202 with an empty body. No challenge was bypassed. Therefore actual raw HTML ingestion was not smoke-tested against the publisher; parser tests use synthetic structural fixtures, not a claim that real HTML ingestion succeeded. Empty/non-200 and missing-article responses fail explicitly. No corpus storage, embedding or inference was performed.

Collection remained bounded: one request in flight, at least two seconds between source requests, no repeated authentication/challenge retries. The adapter uses the existing bounded HTTP helper and scrape semaphore.
