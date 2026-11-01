#!/usr/bin/env python3
"""Strict top-level ActionRecord partitioning for legacy SWF action bytes.

ActionDefineFunction/ActionDefineFunction2 bodies follow their ActionRecord
headers; they are NOT part of the enclosing action stream. This parser only
returns structural metadata. It neither evaluates Flash VM paths nor exports
function names, operands, or body bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct


class ActionStructureError(ValueError):
    """Malformed or unsupported scope: do not claim a verified partition."""


@dataclass(frozen=True)
class TopLevelAction:
    start: int
    opcode: int
    header_end: int
    end: int
    body_start: int | None = None
    body_end: int | None = None


def _string_end(data: bytes, start: int, limit: int) -> int:
    end = data.find(b"\x00", start, limit)
    if end < 0:
        raise ActionStructureError("Unterminated function header string")
    return end + 1


def _function_body_size(data: bytes, opcode: int, start: int, limit: int) -> int:
    cursor = _string_end(data, start, limit)
    if cursor + 2 > limit:
        raise ActionStructureError("Truncated function parameter count")
    count = struct.unpack_from("<H", data, cursor)[0]
    cursor += 2
    if opcode == 0x8E:
        if cursor + 3 > limit:
            raise ActionStructureError("Truncated DefineFunction2 register/flags")
        cursor += 3
    if count > limit - cursor:
        raise ActionStructureError("Function parameter count exceeds header")
    for _ in range(count):
        if opcode == 0x8E:
            if cursor >= limit:
                raise ActionStructureError("Truncated parameter register")
            cursor += 1
        cursor = _string_end(data, cursor, limit)
    if cursor + 2 != limit:
        raise ActionStructureError("Function header length mismatch")
    return struct.unpack_from("<H", data, cursor)[0]


def partition_top_level_actions(data: bytes) -> dict:
    """Partition complete top-level records, skipping declared function bodies.

    An ActionEnd marks a top-level terminator but does not stop parsing later
    bytes: later records are syntactic data, not presumed executable. With and
    Try contain nested blocks not handled here; reject them rather than report
    an incorrectly verified top-level partition.
    """
    records = []
    cursor = 0
    first_end = None
    body_bytes = 0
    while cursor < len(data):
        start = cursor
        opcode = data[cursor]
        if opcode < 0x80:
            header_end = cursor + 1
            operand_start = header_end
        else:
            if cursor + 3 > len(data):
                raise ActionStructureError("Truncated extended ActionRecord header")
            length = struct.unpack_from("<H", data, cursor + 1)[0]
            operand_start = cursor + 3
            header_end = operand_start + length
            if header_end > len(data):
                raise ActionStructureError("ActionRecord operand exceeds action bytes")
        if opcode in (0x94, 0x8F):
            raise ActionStructureError("Unsupported nested With/Try scope")
        body_start = body_end = None
        cursor = header_end
        if opcode in (0x9B, 0x8E):
            body_size = _function_body_size(data, opcode, operand_start, header_end)
            body_start = header_end
            body_end = body_start + body_size
            if body_end > len(data):
                raise ActionStructureError("Declared function body exceeds action bytes")
            cursor = body_end
            body_bytes += body_size
        records.append(TopLevelAction(start, opcode, header_end, cursor, body_start, body_end))
        if opcode == 0 and first_end is None:
            first_end = start
    return {
        "records": tuple(records),
        "first_top_level_action_end_offset": first_end,
        "top_level_record_count": len(records),
        "top_level_post_end_record_count": sum(
            first_end is not None and rec.start > first_end for rec in records
        ),
        "declared_function_count": sum(rec.body_start is not None for rec in records),
        "declared_function_body_byte_total": body_bytes,
        "top_level_partition_verified": True,
        "runtime_reachability_verified": False,
    }
