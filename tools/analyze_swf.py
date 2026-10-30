#!/usr/bin/env python3
"""FFDec analysis for the bundled legacy SWF, with bounded, auditable phases.

The repository's FFDec version does not support the newer '-header' command
or '-dumpAS2 -exportNames'. The SWF header comes from swf_inventory.py.
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
ERROR_MARKERS = (
    "Error: Bad Commandline Arguments!",
    "I/O error during reading",
    "Exception in thread",
    "java.lang.OutOfMemoryError",
)


def java8_version() -> str:
    proc = subprocess.run(
        ["java", "-version"], capture_output=True, text=True,
        errors="replace", timeout=15, check=False,
    )
    version_text = proc.stdout + proc.stderr
    match = re.search(r'version "([^"]+)"', version_text)
    if proc.returncode != 0 or not match or not match.group(1).startswith("1.8"):
        raise RuntimeError("Requires Java 1.8 (Java 8); found: " + version_text.strip()[:300])
    return match.group(1)


def run_command(name: str, ffdec: Path, args: list[str], out: Path, timeout: int) -> dict:
    command = [
        "java", "-Xms256m", "-Xmx3g", "-Djava.awt.headless=true",
        "-Djna.nosys=true", "-jar", str(ffdec), "-cli", *args,
    ]
    logfile = out / f"{name}.log"
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
            timed_out, code = True, None
            log.write(f"\nTIMEOUT: {name} exceeded {timeout} seconds.\n")
    duration = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    log_text = logfile.read_text(encoding="utf-8", errors="replace")
    markers = [marker for marker in ERROR_MARKERS if marker in log_text]
    # Older FFDec prints the entire CLI help and returns 0 for unsupported commands.
    if "Commandline arguments:" in log_text and "Bad Commandline Arguments!" in log_text:
        markers.append("unsupported_command")
    ok = code == 0 and not timed_out and not markers
    print(f"[FFDEC] END {name} status={'PASS' if ok else 'FAIL'} "
          f"exit={code} duration={duration}s errors={markers}", flush=True)
    return {
        "ok": ok, "exit_code": code, "timed_out": timed_out,
        "duration_seconds": duration, "timeout_seconds": timeout,
        "log": str(logfile.relative_to(ROOT)), "args": args,
        "detected_errors": markers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, default=SWF)
    parser.add_argument("--ffdec", type=Path, default=FFDEC)
    parser.add_argument("--output", type=Path, default=ROOT / "build/swf-analysis")
    parser.add_argument("--phase", choices=("inventory", "deep", "scripts", "assets", "all"),
                        default="inventory")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 900:
        parser.error("--timeout must be 10..900 seconds")
    swf, ffdec, out = args.swf.resolve(), args.ffdec.resolve(), args.output.resolve()
    if not swf.is_file() or not ffdec.is_file():
        parser.error("Missing original SWF or FFDec jar")
    out.mkdir(parents=True, exist_ok=True)
    java_version = java8_version()
    manifest = inventory(swf)
    (out / "swf-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    has_as3 = any(tag["tag_code"] in (72, 82) for tag in manifest["scripts"])
    print("[SWF] " + json.dumps({
        "stage": manifest["stage"], "tag_count": manifest["tag_count_including_sprites"],
        "characters": len(manifest["characters"]),
        "script_tags": len(manifest["scripts"]),
        "as3_tag_present": has_as3,
        "unknown_tag_253": manifest["tag_counts_by_code"].get("253", 0),
    }, ensure_ascii=False), flush=True)

    commands = {}
    exports = out / "exports"
    if args.phase in ("inventory", "all"):
        commands["tags"] = run_command(
            "tags", ffdec, ["-dumpSWF", str(swf)], out, args.timeout
        )

    # FFDec 18.0.0 can stall on -dumpAS2 and -linkReport for this 22.9 MB
    # uncompressed AS2 SWF. Keep diagnostics explicit and separately bounded,
    # rather than making the baseline structural check falsely claim success.
    if args.phase in ("deep", "all"):
        specs = [
            ("as1_as2", ["-dumpAS2", str(swf)]),
            ("link_report", [
                "-linkReport", "-outfile", str(out / "link-report.xml"), str(swf)
            ]),
        ]
        if has_as3:
            specs.append(("as3", ["-dumpAS3", str(swf)]))
        for name, command in specs:
            commands[name] = run_command(name, ffdec, command, out, args.timeout)

    if args.phase in ("scripts", "all"):
        commands["script_export"] = run_command(
            "script_export", ffdec, [
                "-timeout", "60", "-exportTimeout", "600",
                "-format", "script:as", "-export", "script",
                str(exports / "scripts"), str(swf),
            ], out, min(900, args.timeout * 8),
        )

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
        for path in exports.rglob("*"):
            if path.is_file():
                counts[path.suffix.lower() or "[no extension]"] += 1
    inventory_ok = commands.get("tags", {}).get("ok") if args.phase in ("inventory", "all") else None
    deep_required = ["as1_as2", "link_report"] + (["as3"] if has_as3 else [])
    deep_ok = all(commands.get(k, {}).get("ok") for k in deep_required) if args.phase in ("deep", "all") else None
    scripts_ok = commands.get("script_export", {}).get("ok") if args.phase in ("scripts", "all") else None
    assets_ok = commands.get("asset_export", {}).get("ok") if args.phase in ("assets", "all") else None
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase, "java_version": java_version,
        "source": manifest["source"], "stage": manifest["stage"],
        "tag_count": manifest["tag_count_including_sprites"],
        "character_count": len(manifest["characters"]),
        "script_tag_count": len(manifest["scripts"]),
        "as3_tag_present": has_as3,
        "unknown_tag_253": manifest["tag_counts_by_code"].get("253", 0),
        "commands": commands, "inventory_complete": inventory_ok,
        "deep_diagnostics_complete": deep_ok,
        "scripts_complete": scripts_ok, "assets_complete": assets_ok,
        "exported_file_count": sum(counts.values()),
        "exported_extensions": dict(sorted(counts.items())),
        "warning": "Original assets and decompiled source are local-only and not published.",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("[RESULT] " + json.dumps({
        "inventory_complete": inventory_ok, "deep_diagnostics_complete": deep_ok,
        "scripts_complete": scripts_ok,
        "assets_complete": assets_ok, "exported_files": sum(counts.values()),
    }), flush=True)
    return 2 if any(x is False for x in (inventory_ok, deep_ok, scripts_ok, assets_ok)) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print("[ERROR] " + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2)
