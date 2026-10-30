#!/usr/bin/env python3
"""Reproducible SWF inventory/export using the repository's FFDec and Java 8."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SWF = ROOT / "拳皇wing1.4.swf"
DEFAULT_FFDEC = ROOT / "FFDec" / "ffdec.jar"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def java_version() -> tuple[str, int]:
    proc = subprocess.run(
        ["java", "-version"], capture_output=True, text=True, check=False
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(r'version "([^"]+)"', output)
    if not match:
        raise RuntimeError("无法读取 Java 版本；请安装 64 位 Java 8。")
    version = match.group(1)
    if version.startswith("1.8"):
        major = 8
    else:
        major_match = re.match(r"(\d+)", version)
        major = int(major_match.group(1)) if major_match else -1
    if major != 8:
        raise RuntimeError(
            "本项目分析环境锁定 Java 1.8；当前版本为 " + version
        )
    return version, major


def run_ffdec(
    ffdec: Path,
    args: list[str],
    log_path: Path,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    command = [
        "java", "-Xms512m", "-Xmx4g", "-Djna.nosys=true",
        "-jar", str(ffdec), "-cli", *args
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
        return {
            "command": command,
            "exit_code": proc.returncode,
            "log": str(log_path.relative_to(ROOT)),
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        output = ""
        if exc.stdout:
            output += exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
        if exc.stderr:
            output += exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output + "\nFFDec command timed out.\n", encoding="utf-8")
        return {
            "command": command,
            "exit_code": None,
            "log": str(log_path.relative_to(ROOT)),
            "ok": False,
            "error": "timeout",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, default=DEFAULT_SWF)
    parser.add_argument("--ffdec", type=Path, default=DEFAULT_FFDEC)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "swf-analysis")
    args = parser.parse_args()

    swf = args.swf.resolve()
    ffdec = args.ffdec.resolve()
    output = args.output.resolve()

    if not swf.is_file():
        raise SystemExit("SWF 文件不存在：" + str(swf))
    if not ffdec.is_file():
        raise SystemExit("FFDec JAR 不存在：" + str(ffdec))

    version, major = java_version()
    with swf.open("rb") as handle:
        header = handle.read(8)
    if len(header) < 8 or header[:3] not in (b"FWS", b"CWS", b"ZWS"):
        raise SystemExit("文件头不是有效的 SWF signature。")

    signature = header[:3].decode("ascii")
    swf_version = header[3]
    declared_length = int.from_bytes(header[4:8], "little")
    output.mkdir(parents=True, exist_ok=True)
    exports = output / "exports"
    exports.mkdir(parents=True, exist_ok=True)

    commands: dict[str, dict[str, Any]] = {}
    commands["header"] = run_ffdec(
        ffdec, ["-header", str(swf)], output / "swf-header.txt"
    )
    commands["tags"] = run_ffdec(
        ffdec, ["-dumpSWF", str(swf)], output / "swf-tags.txt"
    )
    commands["as1_as2"] = run_ffdec(
        ffdec, ["-dumpAS2", "-exportNames", str(swf)],
        output / "as1-as2-scripts.txt"
    )
    commands["as3"] = run_ffdec(
        ffdec, ["-dumpAS3", str(swf)], output / "as3-scripts.txt"
    )
    commands["link_report"] = run_ffdec(
        ffdec, ["-linkReport", "-outfile", str(output / "link-report.xml"), str(swf)],
        output / "link-report.log"
    )
    commands["export"] = run_ffdec(
        ffdec,
        [
            "-format",
            "script:as,shape:svg,image:png_gif_jpeg_alpha,sound:mp3_wav,font:ttf,text:plain",
            "-export",
            "script,image,shape,sound,font,text,binaryData,symbolClass",
            str(exports),
            str(swf),
        ],
        output / "export.log",
        timeout_seconds=3600,
    )

    counts = Counter()
    for path in exports.rglob("*"):
        if path.is_file():
            counts[path.suffix.lower() or "[no extension]"] += 1

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(swf),
            "size_bytes": swf.stat().st_size,
            "sha256": sha256_file(swf),
            "signature": signature,
            "swf_version": swf_version,
            "declared_uncompressed_length": declared_length,
        },
        "runtime": {
            "java_version": version,
            "java_major": major,
            "ffdec_jar": str(ffdec),
        },
        "commands": commands,
        "exported_file_count": sum(counts.values()),
        "exported_extensions": dict(sorted(counts.items())),
        "analysis_complete": all(
            commands[name]["ok"] for name in ("header", "tags", "as1_as2", "export")
        ),
        "notes": [
            "AS3 dump and link report are recorded independently because a legacy SWF may not contain AS3.",
            "Exported original game assets are kept in the analysis output and are not committed automatically.",
        ],
    }
    summary_path = output / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["analysis_complete"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print("SWF analysis failed: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
