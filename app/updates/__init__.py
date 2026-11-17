"""Signed module update channel (WP-111; ARCHITECTURE.md § 3.9).

Static, signed feeds (published as GitHub release assets, or any static
host) carry **parameter sets** and **corpus change notices** for one module
between code releases. The client fetches a feed and its detached signature,
verifies the Ed25519 signature against a locally configured trust anchor
*before* parsing the feed, checks it applies to the installed module version
and is newer than every feed applied before (anti-rollback/replay), and only
then writes ``legal_parameter`` rows plus one ``module_update`` ledger row in
one transaction. No hosted service, no telemetry: fetching is a plain GET of
two static files, nothing is reported back.

* ``signing`` — keys, key ids, signatures, the trust file;
* ``feed`` — feed format ``citizen-update-feed-v1.0`` (schema + parsing);
* ``ledger`` — the ``module_update`` table: applied state, protected rows;
* ``apply`` — fetch → verify → check → apply.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-111: initial version.
