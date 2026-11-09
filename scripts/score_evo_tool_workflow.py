"""Score a saved EVO fixed-file workflow download without executing imported code."""

import argparse
import csv
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from fixed_checks import SCHEMAS, run_checks
from import_evo import strict
from regression import evaluate, exact_json_equal


MAX_BYTES = 5 * 1024 * 1024


def digest(raw):
    return sha256(raw).hexdigest()


def expected_audit():
    return [
        {"tool": "read_table", "arguments": {"path": name, "columns": list(SCHEMAS[name])}, "status": status}
        for name, status in (
            ("movements.csv", "timeout"), ("movements.csv", "ok"), ("invoices.csv", "ok"),
            ("fx.csv", "ok"), ("restricted.csv", "denied"),
        )
    ]


def parse_json(raw):
    return strict(raw.decode("utf-8"))


def frozen_inputs(path):
    manifest = parse_json(path.read_bytes())
    result = {key.removeprefix("inputs/"): value for key, value in manifest.items() if key.startswith("inputs/")}
    needed = {"data/" + name for name in SCHEMAS}
    if not needed <= set(result):
        raise ValueError("Frozen input list is incomplete")
    return result


def read_download(path, hashes, approval):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Archive exceeds size limit")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Archive exceeds size limit")
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 64 or sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise ValueError("Archive exceeds member limits")
        parts = [PurePosixPath(entry.filename).parts for entry in entries]
        prefix = parts[0][0]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", prefix):
            raise ValueError("Invalid archive root")
        files = {}
        for entry, path_parts in zip(entries, parts):
            if (entry.is_dir() or len(path_parts) < 2 or path_parts[0] != prefix
                    or entry.filename != "/".join(path_parts) or ".." in path_parts or "\\" in entry.filename
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unexpected archive member")
            relative = "/".join(path_parts[1:])
            if relative in files:
                raise ValueError("Duplicate archive member")
            files[relative] = entry
        wanted = {"bundle_manifest.json", "solve.py", "output/result.json", "output/run_receipt.json"}
        if set(files) != wanted | {"inputs/" + name for name in hashes}:
            raise ValueError("Download does not contain exactly the expected members")
        declared = parse_json(archive.read(files["bundle_manifest.json"]))
        if declared["run_name"] != prefix or declared["inputs"] != hashes:
            raise ValueError("Bundle manifest disagrees with independent freeze")
        inputs = {name: archive.read(files["inputs/" + name]) for name in hashes}
        if any(digest(value) != hashes[name] for name, value in inputs.items()):
            raise ValueError("Downloaded input bytes disagree with independent freeze")
        source_hash = digest(archive.read(files["solve.py"]))
        approved = re.findall(r"(?mi)^sha256[:：]\s*([a-f0-9]{64})\s*$", approval)
        if approved != [source_hash] or prefix + "/solve.py" not in approval:
            raise ValueError("Source does not match independent approval")
        result = parse_json(archive.read(files["output/result.json"]))
        model_receipt = parse_json(archive.read(files["output/run_receipt.json"]))
    return prefix, result, model_receipt, inputs, source_hash, digest(raw)


def card_evidence(cards, prefix, receipt):
    if cards is None:
        return "not_provided", [], []
    script = re.escape(prefix + "/solve.py")
    calls = re.findall(
        r"(?m)^运行 Python 脚本(已完成|失败)[^\r\n]*?" + script + r" · 已提交运行（runId=([A-Za-z0-9_-]+)）",
        cards,
    )
    statuses = re.findall(r"(?m)^查询脚本状态已调用✅\s*([A-Za-z0-9_-]+) · ([a-z_]+)", cards)
    run_id = receipt.get("run_id")
    if not calls or not statuses:
        status = "incomplete_summary"
    elif ("已完成", run_id) in calls and (run_id, "succeeded") in statuses and receipt.get("status") == "succeeded":
        status = "matched_summary_only"
    else:
        status = "conflict"
    return status, [run for state, run in calls if state == "已完成"], [run for state, run in calls if state == "失败"]


def score(result, expected):
    # Exact decimal value for amounts only. Text IDs, nulls and all other fields
    # remain strict; no missing field can be manufactured by normalization.
    normalized = json.loads(json.dumps(result, allow_nan=False))

    def reconcile(actual, target, key):
        a, b = actual[key], target[key]
        if type(a) in (str, int, float) and type(b) in (str, int, float):
            try:
                x, y = Decimal(str(a)), Decimal(str(b))
                if x.is_finite() and y.is_finite() and x == y:
                    actual[key] = b
            except InvalidOperation:
                pass

    for section, field in (("A", "net_units"), ("B", "cny_by_currency")):
        a = normalized.get(section, {})
        if isinstance(a, dict) and isinstance(a.get(field), dict):
            for key in a[field].keys() & expected[section][field].keys():
                reconcile(a[field], expected[section][field], key)
    if isinstance(normalized.get("B"), dict) and "total_cny" in normalized["B"]:
        reconcile(normalized["B"], expected["B"], "total_cny")
    payload = json.dumps(normalized, ensure_ascii=False, allow_nan=False)
    checks = {}
    for key, value in {**expected, "audit": expected_audit()}.items():
        passed, reasons = evaluate(payload, [{"path": [key], "exact_json": value}])
        checks[key] = {"passed": passed, "reasons": reasons}
    return normalized, checks


def replay_local(inputs):
    """Execute only the trusted, bundled scorer workflow, not the ZIP's Python."""
    observed, opened = [], []
    with TemporaryDirectory() as temp:
        folder = Path(temp)
        for name in ("movements.csv", "invoices.csv", "fx.csv"):
            (folder / name).write_bytes(inputs["data/" + name])
        timeout_pending = True

        def read_table(path, columns):
            nonlocal timeout_pending
            entry = {"tool": "read_table", "arguments": {"path": path, "columns": list(columns)}}
            observed.append(entry)
            if path == "restricted.csv":
                entry.update(status="denied", error={"type": "PermissionError", "message": "Restricted input"})
                raise PermissionError("Restricted input")
            if path == "movements.csv" and timeout_pending:
                timeout_pending = False
                entry.update(status="timeout", error={"type": "TimeoutError", "message": "Planned one-time timeout"})
                raise TimeoutError("Planned one-time timeout")
            with (folder / path).open(encoding="utf-8", newline="") as stream:
                opened.append(path)
                result = [{key: row[key] for key in columns} for row in csv.DictReader(stream)]
            entry.update(status="ok", result=result)
            return result

        result = run_checks(read_table, [])
    result["audit"] = [{key: item[key] for key in ("tool", "arguments", "status")} for item in observed]
    return result, {"origin": "local_replay_not_evo", "opened_files": opened, "calls": observed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "expected", "frozen-manifest", "approval", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cards", type=Path)
    parser.add_argument("--local-replay", action="store_true")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output already exists")
        expected = parse_json(args.expected.read_bytes())
        if set(expected) != {"A", "B", "C"}:
            raise ValueError("Expected answer must contain A, B and C")
        prefix, result, receipt, inputs, script_hash, archive_hash = read_download(
            args.archive, frozen_inputs(args.frozen_manifest), args.approval.read_text(encoding="utf-8")
        )
        card_raw = args.cards.read_bytes() if args.cards else None
        page_status, shown_completed, shown_failed = card_evidence(
            card_raw.decode("utf-8") if card_raw is not None else None, prefix, receipt
        )
        normalized, checks = score(result, expected)
        report = {
            "origin": "evo_downloaded_workflow_artifacts",
            "run_name": prefix, "archive_sha256": archive_hash, "approved_source_sha256": script_hash,
            "reported_run_id": receipt.get("run_id"), "reported_exit_code": receipt.get("exit_code"),
            "reported_receipt_origin": "model_written_artifact", "page_card_status": page_status,
            "page_card_sha256": digest(card_raw) if card_raw is not None else None,
            "page_completed_script_runs": shown_completed, "page_failed_script_runs": shown_failed,
            "native_tool_receipt_verified": False,
            "evidence_note": "Page cards are summaries; local replay responses are not native EVO receipts.",
            "checks": checks,
            "passed_checks": sum(entry["passed"] for entry in checks.values()), "total_checks": len(checks),
            "local_replay": None,
        }
        observed = None
        if args.local_replay:
            local, observed = replay_local(inputs)
            normalized_local, _ = score(local, expected)
            report["local_replay"] = {
                "origin": observed["origin"], "opened_files": observed["opened_files"],
                "calls": len(observed["calls"]), "result_matches_archive": exact_json_equal(normalized_local, normalized),
            }
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        if observed is not None:
            (args.output/"local-tool-responses.json").write_text(
                json.dumps(observed, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
            )
        print(json.dumps({key: report[key] for key in (
            "passed_checks", "total_checks", "page_card_status", "native_tool_receipt_verified", "local_replay"
        )}, ensure_ascii=False))
    except (ValueError, BadZipFile, OSError, RuntimeError, KeyError, IndexError, TypeError, AttributeError) as exc:
        parser.exit(2, f"导入或评分未完成（{type(exc).__name__}）。请核对下载包、独立冻结清单及审批记录。\n")


if __name__ == "__main__":
    main()
