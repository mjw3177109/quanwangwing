#!/usr/bin/env python3
"""Bounded, phase-based FFDec analysis. Never writes to the original SWF.

Phase 'inventory' creates header, tag and script reports; 'assets' performs the
larger resource export separately. Use --phase all for both. Each subprocess
has its own timeout, and logs are written as it runs, so CI can diagnose hangs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from swf_inventory import inventory

ROOT = Path(__file__).resolve().parents[1]
SWF = ROOT / "拳皇wing1.4.swf"
FFDEC = ROOT / "FFDec" / "ffdec.jar"


def java8_version() -> str:
    proc = subprocess.run(
        ["java", "-version"], capture_output=True, text=True,
        errors="replace", timeout=15, check=False,
    )
    text = proc.stdout + proc.stderr
    match = re.search(r'version "([^"]+)"', text)
    if proc.returncode != 0 or not match or not match.group(1).startswith("1.8"):
        raise RuntimeError("Requires Java 1.8 (Java 8); found: " + text.strip()[:300])
    return match.group(1)


def run_command(name: str, ffdec: Path, args: list[str], log_dir: Path, timeout: int) -> dict:
    command = [
        "java", "-Xms256m", "-Xmx3g", "-Djava.awt.headless=true",
        "-Djna.nosys=true", "-jar", str(ffdec), "-cli", *args,
    ]
    logfile = log_dir / f"{name}.log"
    print(f"[FFDEC] START {name} timeout={timeout}s", flush=True)
    started = datetime.now(timezone.utc)
    timed_out = False
    with logfile.open("w", encoding="utf-8", errors="replace") as log:
        try:
            proc = subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                timeout=timeout, check=False,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            code = None
            log.write(f"\nTIMEOUT: {name} exceeded {timeout} seconds.\n")
    duration = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    ok = code == 0 and not timed_out
    print(f"[FFDEC] END {name} status={'PASS' if ok else 'FAIL'} "
          f"exit={code} duration={duration}s log={logfile}", flush=True)
    return {
        "ok": ok, "exit_code": code, "timed_out": timed_out,
        "duration_seconds": duration, "timeout_seconds": timeout,
        "log": str(logfile.relative_to(ROOT)), "args": args,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, default=SWF)
    parser.add_argument("--ffdec", type=Path, default=FFDEC)
    parser.add_argument("--output", type=Path, default=ROOT / "build/swf-analysis")
    parser.add_argument("--phase", choices=("inventory", "assets", "all"), default="inventory")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Seconds per FFDec metadata command (default 120)")
    args = parser.parse_args()
    if args.timeout < 10 or args.timeout > 900:
        parser.error("--timeout must be between 10 and 900 seconds")
    swf, ffdec, out = args.swf.resolve(), args.ffdec.resolve(), args.output.resolve()
    if not swf.is_file() or not ffdec.is_file():
        parser.error("Missing original SWF or FFDec jar")
    out.mkdir(parents=True, exist_ok=True)
    version = java8_version()

    # Pure Python inventory is independent of FFDec and survives FFDec failure.
    manifest = inventory(swf)
    (out / "swf-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("[SWF] header and tag inventory:",
          json.dumps({
              "stage": manifest["stage"],
              "tag_count": manifest["tag_count_including_sprites"],
              "characters": len(manifest["characters"]),
              "scripts": len(manifest["scripts"]),
              "symbols": len(manifest["symbol_class"]),
          }, ensure_ascii=False), flush=True)

    commands = {}
    exports = out / "exports"
    if args.phase in ("inventory", "all"):
        specs = [
            ("header", ["-header", str(swf)], args.timeout),
            ("tags", ["-dumpSWF", str(swf)], args.timeout),
            ("as1_as2", ["-dumpAS2", "-exportNames", str(swf)], args.timeout),
            ("as3", ["-dumpAS3", str(swf)], args.timeout),
            ("link_report", [
                "-linkReport", "-outfile", str(out / "link-report.xml"), str(swf)
            ], args.timeout),
            ("script_export", [
                "-format", "script:as", "-export", "script",
                str(exports / "scripts"), str(swf)
            ], min(900, args.timeout * 3)),
        ]
        for name, command, timeout in specs:
            commands[name] = run_command(name, ffdec, command, out, timeout)

    if args.phase in ("assets", "all"):
        commands["asset_export"] = run_command(
            "asset_export", ffdec, [
                "-format",
                "shape:svg,image:png_gif_jpeg_alpha,sound:mp3_wav,font:ttf,text:plain",
                "-export", "image,shape,sound,font,text,binaryData,symbolClass",
                str(exports / "assets"), str(swf),
            ], out, min(1800, args.timeout * 8),
        )

    counts = Counter()
    if exports.exists():
        for p in exports.rglob("*"):
            if p.is_file():
                counts[p.suffix.lower() or "[no extension]"] += 1
    # A missing AS3 block is not a failure for an AS1/AS2 SWF.
    required = ("header", "tags", "as1_as2", "link_report", "script_export")
    inventory_ok = all(commands.get(k, {}).get("ok") for k in required) if args.phase in ("inventory", "all") else None
    assets_ok = commands.get("asset_export", {}).get("ok") if args.phase in ("assets", "all") else None
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase, "java_version": version,
        "source": manifest["source"], "stage": manifest["stage"],
        "tag_count": manifest["tag_count_including_sprites"],
        "character_count": len(manifest["characters"]),
        "script_tag_count": len(manifest["scripts"]),
        "symbol_count": len(manifest["symbol_class"]),
        "commands": commands, "inventory_complete": inventory_ok,
        "assets_complete": assets_ok,
        "exported_file_count": sum(counts.values()),
        "exported_extensions": dict(sorted(counts.items())),
        "warning": "Exported original assets/scripts are not committed or published automatically.",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "inventory_complete": inventory_ok, "assets_complete": assets_ok,
        "exported_file_count": sum(counts.values()),
    }, ensure_ascii=False), flush=True)
    if inventory_ok is False or assets_ok is False:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print("[ERROR] " + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2)
