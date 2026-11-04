#!/usr/bin/env python3
"""Sanitize FFDec deep-diagnostic results to metadata-only status.

The raw -dumpAS2 output and link-report XML stay on the Actions runner.
This tool emits command status and timing only; it never copies command args,
log paths, error text, ActionScript, or original assets into the artifact.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_BASE = ("as1_as2", "link_report")


def summarize(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Invalid deep diagnostic summary")
    source = data.get("source")
    if not isinstance(source, dict):
        raise ValueError("Missing source metadata")
    source_sha = source.get("sha256")
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise ValueError("Invalid source SHA-256")
    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise ValueError("Missing command metadata")
    as3_present = data.get("as3_tag_present")
    if type(as3_present) is not bool:
        raise ValueError("Invalid AS3 tag flag")
    required = list(REQUIRED_BASE) + (["as3"] if as3_present else [])
    command_status = {}
    for name, item in commands.items():
        if not isinstance(name, str) or not isinstance(item, dict):
            raise ValueError("Invalid command row")
        ok = item.get("ok")
        timed_out = item.get("timed_out")
        exit_code = item.get("exit_code")
        duration = item.get("duration_seconds")
        timeout = item.get("timeout_seconds")
        errors = item.get("detected_errors", [])
        if type(ok) is not bool or type(timed_out) is not bool:
            raise ValueError("Invalid command outcome")
        if exit_code is not None and type(exit_code) is not int:
            raise ValueError("Invalid command exit code")
        if type(duration) not in (int, float) or duration < 0:
            raise ValueError("Invalid command duration")
        if type(timeout) is not int or timeout < 1:
            raise ValueError("Invalid command timeout")
        if not isinstance(errors, list):
            raise ValueError("Invalid detected error list")
        command_status[name] = {
            "ok": ok,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_seconds": round(float(duration), 3),
            "timeout_seconds": timeout,
            "detected_error_count": len(errors),
        }
    present = all(name in command_status for name in required)
    successful = present and all(
        command_status[name]["ok"]
        and command_status[name]["exit_code"] == 0
        and not command_status[name]["timed_out"]
        and command_status[name]["detected_error_count"] == 0
        for name in required
    )
    phase_ok = data.get("phase") == "deep"
    complete = (phase_ok and successful
                and data.get("deep_diagnostics_complete") is True)
    return {
        "source_sha256": source_sha,
        "source_size_bytes": source.get("size_bytes"),
        "phase": data.get("phase"),
        "java_version": data.get("java_version"),
        "as3_tag_present": as3_present,
        "required_commands": required,
        "required_commands_present": present,
        "required_commands_successful": successful,
        "deep_diagnostics_complete": complete,
        "status": "success" if complete else "incomplete",
        "commands": command_status,
        "runtime_binding_verified": False,
        "execution_verified": False,
        "limitations": [
            "Only FFDec command outcome, duration and timeout metadata are emitted.",
            "Raw ActionScript dumps, link-report XML, command logs and original assets stay on the runner.",
            "A successful dump or link report is not proof of recovered runtime behavior.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.summary.is_file():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "status": "missing_summary",
            "deep_diagnostics_complete": False,
            "runtime_binding_verified": False,
            "execution_verified": False,
        }, indent=2) + "\n", encoding="utf-8")
        print("Deep diagnostics summary is missing")
        return 1
    data = json.loads(args.summary.read_text(encoding="utf-8"))
    result = summarize(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "required_commands": result["required_commands"],
        "required_commands_present": result["required_commands_present"],
        "required_commands_successful": result["required_commands_successful"],
        "deep_diagnostics_complete": result["deep_diagnostics_complete"],
        "commands": result["commands"],
    }, ensure_ascii=False))
    return 0 if result["deep_diagnostics_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
