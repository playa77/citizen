#!/usr/bin/env python3
"""Benchmark the /api/v1/analyze endpoint with SSE streaming timing.

Posts a 1500-word sample text and records:
- Time to first SSE event
- Time per stage event
- Time to final event
- Total connection duration

Usage:
    python scripts/benchmark_analyze.py [--base-url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import AsyncGenerator

import httpx

# ---------------------------------------------------------------------------
# Default sample text (~1500 words of plausible German legal content)
# ---------------------------------------------------------------------------

_SAMPLE_TEXT = """
Betreff: Widerspruch gegen den Bescheid vom 15.03.2026 – Az. 12345/2026

Sehr geehrte Damen und Herren,

hiermit lege ich Widerspruch gegen Ihren Bescheid vom 15. März 2026
(Aktenzeichen 12345/2026) ein, mit dem Sie meinen Antrag auf Leistungen
zur Sicherung des Lebensunterhalts nach dem Zweiten Buch Sozialgesetzbuch
(SGB II) teilweise abgelehnt haben.

Sachverhalt:
Am 10.02.2026 habe ich einen Antrag auf Leistungen nach dem SGB II gestellt.
In diesem Antrag habe ich meine Einkommens- und Vermögensverhältnisse
vollständig und wahrheitsgemäß dargelegt. Ich beziehe derzeit kein
regelmäßiges Einkommen und verfüge über kein nennenswertes Vermögen.
Meine monatlichen Kosten der Unterkunft belaufen sich auf 650,00 Euro
(Kaltmiete 480,00 Euro zuzüglich Nebenkosten von 120,00 Euro sowie
Heizkosten in Höhe von 50,00 Euro). Ich bewohne eine Wohnung mit einer
Wohnfläche von 55 Quadratmetern. Dies entspricht den angemessenen
Wohnverhältnissen gemäß den Richtlinien meines örtlichen Jobcenters.

Mit Bescheid vom 15.03.2026 wurden mir Leistungen in Höhe von lediglich
502,00 Euro monatlich bewilligt. Dabei wurden die tatsächlichen Kosten
der Unterkunft nicht in voller Höhe berücksichtigt. Stattdessen hat das
Jobcenter nur einen Betrag von 380,00 Euro für die Unterkunftskosten
anerkannt, ohne dies ausreichend zu begründen. Die Differenz zu meinen
tatsächlichen Kosten beträgt somit 270,00 Euro monatlich, was für mich
eine erhebliche finanzielle Belastung darstellt.

Des Weiteren wurde mir eine Sanktion in Höhe von 30 Prozent des
maßgeblichen Regelbedarfs für den Zeitraum vom 01.04.2026 bis zum
30.06.2026 auferlegt. Diese Sanktion wurde mit einer angeblichen
Meldeversäumnis gemäß § 32 SGB II begründet. Ich bestreite jedoch,
eine Meldeaufforderung erhalten zu haben. Eine entsprechende
Rechtsbehelfsbelehrung lag dem Bescheid entgegen § 36 SGB X ebenfalls
nicht bei. Ich habe keine Kenntnis von einem Termin, zu dem ich hätte
erscheinen sollen. Nach meiner Auffassung liegt ein Verstoß gegen den
Grundsatz des rechtlichen Gehörs nach § 24 SGB X vor, da mir vor Erlass
des Sanktionsbescheids keine Gelegenheit zur Stellungnahme gegeben wurde.

Auch die Eingliederungsvereinbarung vom 05.01.2026 wurde aus meiner Sicht
nicht ordnungsgemäß zustande gebracht. Mir wurde keine angemessene
Bedenkzeit eingeräumt, und ich wurde nicht ausreichend über meine Rechte
und Pflichten aufgeklärt. Ich bin der Auffassung, dass die
Eingliederungsvereinbarung daher möglicherweise unwirksam ist. Nach
§ 15 SGB II soll die Eingliederungsvereinbarung die Eigenverantwortung
der leistungsberechtigten Person stärken und einvernehmlich geschlossen
werden. Beides war hier nicht der Fall.

Zudem wurde mir der Zugang zu Leistungen zur Eingliederung in Arbeit
nach § 16 SGB II verwehrt mit der Begründung, dass hierfür keine
Mittel zur Verfügung stünden. Ich halte dies für rechtswidrig, da
ein Anspruch auf Förderung nach dem SGB II besteht, wenn die
gesetzlichen Voraussetzungen erfüllt sind. Eine pauschale Ablehnung
aus Haushaltsgründen ist meines Erachtens nicht zulässig.

Widerspruchsbegründung:
1. Die Kürzung der Kosten der Unterkunft ist rechtswidrig, da die
   tatsächlichen Aufwendungen für eine angemessene Wohnung nach § 22
   Abs. 1 SGB II in tatsächlicher Höhe zu übernehmen sind, soweit
   sie angemessen sind. Eine substantiierte Begründung für die Kürzung
   fehlt im Bescheid vollständig.

2. Die Sanktion nach § 32 SGB II ist mangels nachweisbarer
   Meldeaufforderung und mangels vorheriger Anhörung rechtswidrig.
   Nach § 24 SGB X ist dem Betroffenen vor Erlass eines belastenden
   Verwaltungsakts Gelegenheit zur Stellungnahme zu geben.

3. Die Ablehnung von Eingliederungsleistungen wegen angeblichen
   Mittel Mangels ist nicht durch § 16 SGB II gedeckt. Ein
   Haushaltsvorbehalt allein rechtfertigt keine Ablehnung von
   Pflichtleistungen.

4. Für den Fall, dass die Eingliederungsvereinbarung unwirksam ist,
   sind die darin festgelegten Pflichten nicht durchsetzbar.
   Dies ist insbesondere für die Bewertung von Pflichtverletzungen
   nach § 31 SGB II von Bedeutung.

5. Eine Gesundheitsprüfung nach § 59 SGB II in Verbindung mit § 62
   SGB II wurde mir zugemutet, ohne dass die gesetzlichen
   Voraussetzungen hierfür vorlagen. Ich bin nicht verpflichtet, mich
   ohne konkreten Anlass einer ärztlichen Untersuchung zu unterziehen.

6. Die Berechnung meines Einkommens erfolgte fehlerhaft. Insbesondere
   wurden Freibeträge nach § 11b SGB II nicht oder nur unzureichend
   berücksichtigt. Die Absetzbeträge für notwendige Versicherungen
   und Werbungskosten wurden nicht in Abzug gebracht.

7. Die Rechtsbehelfsbelehrung im Bescheid ist unvollständig und
   entspricht nicht den Anforderungen des § 36 SGB X. Eine
   ordnungsgemäße Rechtsbehelfsbelehrung muss Angaben zum Rechtsbehelf,
   zur einzuhaltenden Frist und zur zuständigen Behörde enthalten.

8. Die Bewilligung von Leistungen für den Bewilligungszeitraum vom
   01.04.2026 bis zum 30.09.2026 erfolgte unter dem Vorbehalt der
   Rückforderung, was nach § 40 SGB II in Verbindung mit § 328 SGB III
   nicht zulässig ist, da keine vorläufige Entscheidung beantragt wurde.

Ich fordere Sie auf, den Bescheid vom 15.03.2026 aufzuheben und mir die
vollen Leistungen nach dem SGB II zu bewilligen. Insbesondere fordere ich
die vollständige Übernahme meiner Kosten der Unterkunft und die Aufhebung
der Sanktion. Darüber hinaus fordere ich die Bewilligung angemessener
Eingliederungsleistungen.

Bitte bestätigen Sie den Eingang dieses Widerspruchs schriftlich und
teilen Sie mir mit, welche weiteren Unterlagen Sie benötigen.

Mit freundlichen Grüßen
Max Mustermann
""".strip()


def _word_count(text: str) -> int:
    return len(text.split())


def _print_header(title: str) -> None:
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


async def _stream_sse(
    client: httpx.AsyncClient,
    base_url: str,
    text: str,
    disclaimer_version: str,
) -> AsyncGenerator[tuple[float, str], None]:
    """POST to /api/v1/analyze and yield (elapsed_s, raw_sse_line) tuples."""
    url = f"{base_url.rstrip('/')}/api/v1/analyze"
    headers = {
        "Content-Type": "application/json",
        "X-Disclaimer-Ack": disclaimer_version,
    }
    start = time.monotonic()

    async with client.stream(
        "POST",
        url,
        json={"text": text},
        headers=headers,
        timeout=300.0,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            elapsed = time.monotonic() - start
            yield elapsed, line

    yield (time.monotonic() - start, "")  # final elapsed with empty line


async def run_benchmark(
    base_url: str = "http://localhost:8000",
    disclaimer_version: str = "v0.1.0",
    text: str | None = None,
) -> dict[str, float]:
    """Run the benchmark and return timing dictionary."""
    if text is None:
        text = _SAMPLE_TEXT

    word_cnt = _word_count(text)
    print(f"Sample text: {word_cnt} words, {len(text)} characters")
    print(f"Target: {base_url.rstrip('/')}/api/v1/analyze")
    print("Connecting...")

    stage_events: list[tuple[str, float]] = []
    first_event_time: float | None = None
    final_event_time: float | None = None
    total_time: float = 0.0

    async with httpx.AsyncClient(timeout=300.0) as client:
        async for elapsed, line in _stream_sse(
            client, base_url, text, disclaimer_version
        ):
            if line == "" and elapsed < 0.01:
                # End of stream marker
                continue

            if not line.startswith("data: "):
                continue

            # Record first event time
            if first_event_time is None:
                first_event_time = elapsed

            total_time = elapsed

            # Parse SSE payload
            try:
                payload_str = line[6:].strip()
                parsed = json.loads(payload_str)
                stage = parsed.get("stage")

                if stage and parsed.get("status") == "complete":
                    stage_events.append((stage, elapsed))
                elif "final_output" in parsed or "sections" in parsed:
                    final_event_time = elapsed
                elif "error" in parsed:
                    print(f"\nERROR: {parsed}")
                    break
            except (json.JSONDecodeError, KeyError):
                pass

    # Print results
    _print_header("BENCHMARK RESULTS")

    if first_event_time is not None:
        print(f"  Time to first SSE event:    {first_event_time:8.2f}s")

    # Print per-stage timings
    for stage, ts in stage_events:
        print(f"  Stage {stage:<18} {ts:8.2f}s")

    if final_event_time is not None:
        print(f"  Time to final event:        {final_event_time:8.2f}s")

    print(f"{' ' * 42}")
    print(f"  {'Total connection duration:':<30} {total_time:8.2f}s")

    # Coalesce stage timings (SSE events carry cumulative timestamps, so
    # later stages show later times. The benchmark script records wall-clock
    # time at event arrival, so each stage time is the cumulative time
    # from the start. For a cleaner display, show the stage-level latencies
    # as recorded in the SSE payload duration_ms field if available.)
    if len(stage_events) >= 2:
        _print_header("STAGE DELTAS (SSE arrival time diffs)")
        prev_ts: float = 0.0
        for stage, ts in stage_events:
            delta = ts - prev_ts
            print(f"  {stage:<20} {delta:8.2f}s  (cumulative: {ts:.2f}s)")
            prev_ts = ts

    return {
        "first_event_s": first_event_time or 0.0,
        "final_event_s": final_event_time or 0.0,
        "total_s": total_time,
        "stages": {s: t for s, t in stage_events},
        "word_count": word_cnt,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the Citizen /api/v1/analyze endpoint"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the Citizen API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--disclaimer-version",
        default="v0.1.0",
        help="Disclaimer version header value (default: v0.1.0)",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Path to a file containing text to analyze (default: built-in sample)",
    )

    args = parser.parse_args()

    text: str | None = None
    if args.input_file:
        try:
            with open(args.input_file, encoding="utf-8") as f:
                text = f.read().strip()
        except FileNotFoundError:
            print(f"Error: file not found: {args.input_file}")
            sys.exit(1)

    try:
        import asyncio

        asyncio.run(
            run_benchmark(
                base_url=args.base_url,
                disclaimer_version=args.disclaimer_version,
                text=text,
            )
        )
    except httpx.ConnectError:
        print(
            f"\nError: Could not connect to {args.base_url}. "
            f"Is the server running?"
        )
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP error: {exc.response.status_code} {exc.response.text[:500]}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")
        sys.exit(1)

    _print_header("DONE")


if __name__ == "__main__":
    main()
