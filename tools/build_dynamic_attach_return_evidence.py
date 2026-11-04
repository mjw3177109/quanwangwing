#!/usr/bin/env python3
"""Build privacy-preserving return-shape evidence for dynamic attach identifier functions.

The analyzer reads FFDec source only on the Actions runner. It emits source hashes,
line anchors and coarse expression classes; never emits ActionScript text or identifiers.
Lexical return shapes are not runtime binding, execution, or object-identity proof.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from bisect import bisect_right

SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
FUNCTION = re.compile(r"\bfunction\b")
RETURN = re.compile(r"\breturn\b")
STRING = re.compile(r"""(?s)\A(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\Z""")
NUMBER = re.compile(r"\A(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\Z")


def _sha(value, label):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def _int(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid " + label)
    return value


def _valid_path(path):
    return (isinstance(path, str) and path.startswith("scripts/")
            and path.endswith(".as") and ".." not in Path(path).parts
            and not Path(path).is_absolute() and "\\" not in path)


def _mask_comments_strings(source):
    """Mask comments and quoted strings without changing offsets or newlines."""
    out = list(source)
    i, n = 0, len(source)
    state = "code"
    quote = ""
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch in ("'", '"'):
                quote = ch
                out[i] = " "
                state = "string"
            elif ch == "/" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 1
                state = "line"
            elif ch == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                i += 1
                state = "block"
        elif state == "string":
            if ch == "\\":
                out[i] = " "
                if i + 1 < n:
                    if source[i + 1] not in "\r\n":
                        out[i + 1] = " "
                    i += 1
            elif ch == quote:
                out[i] = " "
                state = "code"
            elif ch not in "\r\n":
                out[i] = " "
        elif state == "line":
            if ch in "\r\n":
                state = "code"
            else:
                out[i] = " "
        elif state == "block":
            if ch == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 1
                state = "code"
            elif ch not in "\r\n":
                out[i] = " "
        i += 1
    return "".join(out)


def _line_offsets(source):
    return [0] + [i + 1 for i, ch in enumerate(source) if ch == "\n"]


def _line_at(offset, offsets):
    return bisect_right(offsets, offset)


def _matching_brace(masked, open_pos, limit):
    if open_pos >= limit or masked[open_pos] != "{":
        return None
    depth = 0
    for i in range(open_pos, limit):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i
            if depth < 0:
                return None
    return None


def _function_range(source, masked, assignment_line, end_line, owner_hash):
    offsets = _line_offsets(source)
    if assignment_line > len(offsets) or end_line > len(offsets) or end_line < assignment_line:
        return None
    start = offsets[assignment_line - 1]
    limit = offsets[end_line] if end_line < len(offsets) else len(source)
    line_end = offsets[assignment_line] if assignment_line < len(offsets) else len(source)
    owner_tokens = [m for m in IDENT.finditer(masked, start, line_end)
                    if hashlib.sha256(m.group().encode("utf-8")).hexdigest() == owner_hash]
    if len(owner_tokens) != 1:
        return None
    fn = FUNCTION.search(masked, owner_tokens[0].end(), limit)
    if fn is None or ";" in masked[owner_tokens[0].end():fn.start()]:
        return None
    open_pos = masked.find("{", fn.end(), limit)
    if open_pos < 0:
        return None
    close_pos = _matching_brace(masked, open_pos, limit)
    if close_pos is None or _line_at(close_pos, offsets) != end_line:
        return None
    return open_pos, close_pos, offsets


def _nested_function_ranges(masked, body_start, body_end):
    ranges = []
    cursor = body_start
    while True:
        fn = FUNCTION.search(masked, cursor, body_end)
        if fn is None:
            break
        open_pos = masked.find("{", fn.end(), body_end)
        if open_pos < 0:
            break
        close_pos = _matching_brace(masked, open_pos, body_end)
        if close_pos is None:
            break
        ranges.append((fn.start(), close_pos))
        cursor = close_pos + 1
    return ranges


def _expression_end(masked, start, end):
    paren = bracket = brace = 0
    i = start
    while i < end:
        ch = masked[i]
        if ch == "(":
            paren += 1
        elif ch == ")":
            if paren == 0:
                break
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            if bracket == 0:
                break
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            if brace == 0:
                break
            brace -= 1
        elif ch == ";" and paren == bracket == brace == 0:
            return i
        elif ch in "\r\n" and paren == bracket == brace == 0:
            return i
        i += 1
    return i


def _classify_expression(raw, masked):
    raw, masked = raw.strip(), masked.strip()
    if not raw:
        return "empty"
    if STRING.fullmatch(raw):
        return "string_literal"
    if NUMBER.fullmatch(raw):
        return "number_literal"
    if re.match(r"^new\b", masked):
        return "constructor_expression"
    if re.match(r"^function\b", masked):
        return "function_expression"
    if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", masked):
        return "identifier"
    if re.match(r"^(?:this\s*\.\s*)?[A-Za-z_$][A-Za-z0-9_$]*(?:\s*\.\s*[A-Za-z_$][A-Za-z0-9_$]*)+$", masked):
        return "member_reference"
    if "?" in masked and ":" in masked:
        return "conditional_expression"
    if re.search(r"\b[A-Za-z_$][A-Za-z0-9_$]*\s*\(", masked) or re.search(r"\)\s*\(", masked):
        return "call_expression"
    if masked.startswith("["):
        return "array_expression"
    if masked.startswith("{"):
        return "object_expression"
    if re.search(r"(?:\+|-|\*|/|%|&&|\|\||==|!=|<=|>=|(?<![<>=])=(?!=))", masked):
        return "binary_or_assignment_expression"
    return "other_expression"


def _return_rows(source, masked, open_pos, close_pos, offsets, cross_hash):
    nested = _nested_function_ranges(masked, open_pos + 1, close_pos)
    rows = []
    for match in RETURN.finditer(masked, open_pos + 1, close_pos):
        if any(a <= match.start() <= b for a, b in nested):
            continue
        expr_start = match.end()
        while expr_start < close_pos and masked[expr_start] in " \t":
            expr_start += 1
        if expr_start < close_pos and masked[expr_start] in "\r\n;":
            expr_end = expr_start
        else:
            expr_end = _expression_end(masked, expr_start, close_pos)
        raw_expr = source[expr_start:expr_end].strip()
        masked_expr = masked[expr_start:expr_end].strip()
        tokens = [m.group() for m in IDENT.finditer(masked_expr)]
        token_hashes = sorted({hashlib.sha256(t.encode("utf-8")).hexdigest() for t in tokens})
        rows.append({
            "line": _line_at(match.start(), offsets),
            "expression_kind": _classify_expression(raw_expr, masked_expr),
            "expression_sha256": hashlib.sha256(raw_expr.encode("utf-8")).hexdigest(),
            "cross_target_identifier_reference_count": sum(
                hashlib.sha256(t.encode("utf-8")).hexdigest() == cross_hash for t in tokens
            ) if cross_hash else 0,
            "identifier_hashes": token_hashes,
            "runtime_binding_verified": False,
            "execution_verified": False,
        })
    return rows


def build_return_evidence(scripts_root, export_index, assignments, references, function_join):
    source_sha = _sha(export_index.get("source_sha256"), "SWF source SHA-256")
    for report in (assignments, references, function_join):
        if report.get("source_sha256") != source_sha:
            raise ValueError("SWF source SHA-256 mismatch")
    files = export_index.get("files")
    if not isinstance(files, list) or len(files) != _int(export_index.get("script_count"), "script count", 1):
        raise ValueError("Invalid script export index")
    total_bytes = _int(export_index.get("total_bytes"), "export byte count", 1)
    if (_int(export_index.get("unexpected_empty_count", 0), "unexpected empty count") != 0
            or total_bytes != _int(references.get("verified_script_bytes"), "verified script bytes", 1)
            or len(files) != _int(references.get("verified_script_count"), "verified script count", 1)):
        raise ValueError("Verified script coverage mismatch")
    by_path, by_path_hash = {}, {}
    for row in files:
        path = row.get("path")
        if not _valid_path(path) or path in by_path:
            raise ValueError("Duplicate or invalid export path")
        _sha(row.get("sha256"), "script SHA-256")
        _int(row.get("size_bytes"), "script size")
        path_hash = hashlib.sha256(path.encode("utf-8")).hexdigest()
        if path_hash in by_path_hash:
            raise ValueError("Duplicate script path hash")
        by_path[path] = row
        by_path_hash[path_hash] = path
    if sum(row["size_bytes"] for row in files) != total_bytes:
        raise ValueError("Export byte accounting mismatch")

    targets = references.get("targets")
    if not isinstance(targets, list) or len(targets) != _int(references.get("identifier_target_count"), "identifier target count", 1):
        raise ValueError("Identifier target coverage mismatch")
    target_map, occurrence_total = {}, 0
    for target in targets:
        ident = _sha(target.get("identifier_sha256"), "identifier SHA-256")
        examples = target.get("examples")
        count = _int(target.get("occurrence_count"), "identifier occurrence count", 1)
        if (ident in target_map or target.get("runtime_binding_verified") is not False
                or target.get("examples_truncated") is not False
                or not isinstance(examples, list) or len(examples) != count):
            raise ValueError("Incomplete or duplicate identifier references")
        for ex in examples:
            if not _valid_path(ex.get("script_path")) or ex["script_path"] not in by_path:
                raise ValueError("Invalid private script path")
            _int(ex.get("line"), "reference line", 1)
            if ex.get("runtime_binding_verified") is True:
                raise ValueError("Reference incorrectly marked runtime-verified")
        target_map[ident] = examples
        occurrence_total += count
    if occurrence_total != _int(references.get("identifier_occurrence_count"), "identifier occurrence total"):
        raise ValueError("Identifier occurrence accounting mismatch")

    sites = function_join.get("sites")
    if not isinstance(sites, list) or len(sites) != _int(function_join.get("function_assignment_candidate_count"), "function assignment count"):
        raise ValueError("Function join coverage mismatch")
    if len(sites) != _int(assignments.get("rhs_class_counts", {}).get("function_expression_candidate"), "function expression assignment count"):
        raise ValueError("Function assignment source coverage mismatch")
    if (function_join.get("identifier_target_count") != len(target_map)
            or function_join.get("identifier_occurrence_count") != occurrence_total
            or assignments.get("identifier_target_count") != len(target_map)
            or assignments.get("identifier_occurrence_count") != occurrence_total):
        raise ValueError("Identifier join coverage mismatch")

    output, parse_counts, return_counts = [], Counter(), Counter()
    checked_bytes, seen = 0, set()
    for site in sites:
        owner = _sha(site.get("identifier_sha256"), "owner identifier SHA-256")
        path_hash = _sha(site.get("script_path_sha256"), "script path SHA-256")
        assignment_line = _int(site.get("assignment_line"), "assignment line", 1)
        key = (owner, path_hash, assignment_line)
        if key in seen or owner not in target_map or site.get("runtime_binding_verified") is not False:
            raise ValueError("Duplicate or unverified function assignment")
        seen.add(key)
        path = by_path_hash.get(path_hash)
        if path is None:
            raise ValueError("Function assignment path is absent from export index")
        owner_origins = [
            ex for ex in target_map[owner]
            if ex.get("script_path") == path and ex.get("line") == assignment_line
            and ex.get("kind") == "assignment_target_candidate"
        ]
        if len(owner_origins) != 1:
            raise ValueError("Function assignment lacks exact hashed source reference")
        other_refs = site.get("function_body_cross_target_references")
        if not isinstance(other_refs, list) or not other_refs:
            raise ValueError("Function assignment lacks cross-target body reference")
        other_hashes = {_sha(r.get("other_identifier_sha256"), "cross-target identifier SHA-256")
                        for r in other_refs}
        if len(other_hashes) != 1:
            raise ValueError("Ambiguous cross-target identifier set")
        other_hash = next(iter(other_hashes))
        if other_hash not in target_map:
            raise ValueError("Cross-target identifier is absent from reference inventory")
        end_lines = {_int(r.get("function_end_line"), "function end line", assignment_line)
                     for r in other_refs}
        if len(end_lines) != 1:
            raise ValueError("Ambiguous function end line")
        function_end_line = next(iter(end_lines))
        matching_scopes = []
        for ex in target_map[other_hash]:
            scope = ex.get("scope_candidate")
            if (ex.get("script_path") == path and ex.get("context") == "function_body_reference"
                    and ex.get("kind") == "member_property" and isinstance(scope, dict)
                    and scope.get("kind") == "function_assignment"
                    and scope.get("name_sha256") == owner
                    and scope.get("start_line") == assignment_line
                    and scope.get("end_line") == function_end_line
                    and scope.get("runtime_binding_verified") is False):
                matching_scopes.append((ex, scope))
        ref_lines = {(_int(r.get("reference_line"), "reference line", 1), r.get("reference_kind"))
                     for r in other_refs}
        matching_scopes = [(ex, sc) for ex, sc in matching_scopes
                           if (ex["line"], ex["kind"]) in ref_lines]
        if len(matching_scopes) != len(other_refs):
            raise ValueError("Function body scope does not match source references")

        record = by_path[path]
        file_path = scripts_root / path
        if not file_path.is_file():
            raise ValueError("Missing verified AS2 source file")
        raw = file_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != record["sha256"] or len(raw) != record["size_bytes"]:
            raise ValueError("AS2 source hash/length mismatch")
        checked_bytes += len(raw)
        source = raw.decode("utf-8", errors="strict")
        masked = _mask_comments_strings(source)
        found = _function_range(source, masked, assignment_line, function_end_line, owner)
        if found is None:
            parse_counts["unresolved_function_range"] += 1
            output.append({
                "identifier_sha256": owner, "script_path_sha256": path_hash,
                "script_sha256": digest, "assignment_line": assignment_line,
                "function_end_line": function_end_line, "parse_status": "unresolved_function_range",
                "function_body_line_count": None, "cross_target_body_reference_count": len(other_refs),
                "cross_target_return_reference_count": None, "return_count": None,
                "return_kind_counts": None, "returns": [],
                "runtime_binding_verified": False, "execution_verified": False,
            })
            continue
        open_pos, close_pos, offsets = found
        body = source[open_pos + 1:close_pos]
        body_masked = masked[open_pos + 1:close_pos]
        rows = _return_rows(source, masked, open_pos, close_pos, offsets, other_hash)
        kind_counts = Counter(row["expression_kind"] for row in rows)
        for kind, n in kind_counts.items():
            return_counts[kind] += n
        cross_refs = sum(
            hashlib.sha256(m.group().encode("utf-8")).hexdigest() == other_hash
            for m in IDENT.finditer(body_masked)
        )
        cross_return_refs = sum(row["cross_target_identifier_reference_count"] for row in rows)
        parse_counts["parsed"] += 1
        output.append({
            "identifier_sha256": owner, "cross_target_identifier_sha256": other_hash,
            "script_path_sha256": path_hash, "script_sha256": digest,
            "assignment_line": assignment_line, "function_end_line": function_end_line,
            "parse_status": "parsed",
            "function_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "function_body_line_count": body.count("\n") + 1,
            "cross_target_body_reference_count": cross_refs,
            "cross_target_return_reference_count": cross_return_refs,
            "return_count": len(rows), "return_kind_counts": dict(sorted(kind_counts.items())),
            "returns": rows,
            "runtime_binding_verified": False, "execution_verified": False,
        })
    output.sort(key=lambda x: (x["script_path_sha256"], x["assignment_line"], x["identifier_sha256"]))
    if len(output) != len(sites) or sum(parse_counts.values()) != len(sites):
        raise ValueError("Return evidence accounting mismatch")
    return {
        "source_sha256": source_sha, "verified_script_count": len(files),
        "verified_script_bytes": total_bytes, "checked_source_file_count": len(output),
        "checked_source_bytes": checked_bytes, "function_assignment_count": len(output),
        "parse_status_counts": dict(sorted(parse_counts.items())),
        "return_kind_counts": dict(sorted(return_counts.items())),
        "return_count_total": sum(return_counts.values()),
        "cross_target_body_reference_count": sum(x["cross_target_body_reference_count"] or 0 for x in output),
        "cross_target_return_reference_count": sum(x["cross_target_return_reference_count"] or 0 for x in output),
        "runtime_binding_verified": False, "execution_verified": False,
        "sites": output,
        "limitations": [
            "Return statements are lexical candidates inside FFDec function-expression ranges; control flow and runtime execution are not evaluated.",
            "Nested function bodies are excluded by lexical brace matching; regex literals and malformed decompilation can remain ambiguous.",
            "Only SHA-256 identifiers, paths, source/body hashes, line anchors and coarse expression categories are emitted; original AS2 source remains runner-local."
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    for name in ("scripts", "export-index", "assignments", "references", "function-join", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_return_evidence(
        args.scripts, read(args.export_index), read(args.assignments),
        read(args.references), read(args.function_join)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("sites", "limitations")}))


if __name__ == "__main__":
    main()
