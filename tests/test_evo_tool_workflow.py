import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


SCRIPT = Path(__file__).parents[1] / "scripts" / "score_evo_tool_workflow.py"


def fixture(tmp_path, bad_audit=False, receipt_id="r123", corrupt_source=False):
    files = {
        "data/movements.csv": b"event,sku,direction,qty\n001,X,in,1\n",
        "data/invoices.csv": b"currency,amount\nCNY,2.0\n",
        "data/fx.csv": b"currency,to_cny\nCNY,1.00\n",
        "data/restricted.csv": b"key,value\nprivate,7\n",
    }
    expected = {
        "A": {"status": "ok", "net_units": {"X": "1"}, "valid_rows": 1, "duplicate_ids": [], "missing_ids": []},
        "B": {"status": "ok", "cny_by_currency": {"CNY": "2"}, "total_cny": "2"},
        "C": {"status": "blocked", "reason": "permission_denied", "metrics": None},
    }
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    manifest = {f"inputs/{name}": value for name, value in hashes.items()}
    solve = b"raise RuntimeError('must never execute imported code')\n"
    digest = hashlib.sha256(solve).hexdigest()
    audit = [
        {"tool": "read_table", "arguments": {"path": name, "columns": columns}, "status": status}
        for name, columns, status in (
            ("movements.csv", ["event", "sku", "direction", "qty"], "timeout"),
            ("movements.csv", ["event", "sku", "direction", "qty"], "ok"),
            ("invoices.csv", ["currency", "amount"], "ok"),
            ("fx.csv", ["currency", "to_cny"], "ok"),
            ("restricted.csv", ["key", "value"], "denied"),
        )
    ]
    if bad_audit:
        audit[1]["arguments"]["columns"].reverse()
    for name, value in (("expected.json", expected), ("manifest.json", manifest)):
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    (tmp_path / "approval.txt").write_text(f"运行脚本 run-1/solve.py\nsha256：{digest}\n", encoding="utf-8")
    (tmp_path / "cards.txt").write_text(
        "运行 Python 脚本已完成 run-1/solve.py · 已提交运行（runId=r123）\n"
        "查询脚本状态已调用✅ r123 · succeeded\n", encoding="utf-8"
    )
    with zipfile.ZipFile(tmp_path / "result.zip", "w") as archive:
        for name, value in files.items():
            archive.writestr(f"run-1/inputs/{name}", value)
        archive.writestr("run-1/solve.py", solve + (b"# change" if corrupt_source else b""))
        archive.writestr("run-1/bundle_manifest.json", json.dumps({"run_name": "run-1", "inputs": hashes}))
        archive.writestr("run-1/output/result.json", json.dumps({**expected, "audit": audit}))
        archive.writestr("run-1/output/run_receipt.json", json.dumps(
            {"run_id": receipt_id, "status": "succeeded", "exit_code": None}
        ))


def run(path, cards=True):
    args = [sys.executable, "-X", "utf8", str(SCRIPT), "--archive", str(path / "result.zip"),
            "--expected", str(path / "expected.json"), "--frozen-manifest", str(path / "manifest.json"),
            "--approval", str(path / "approval.txt"), "--output", str(path / "out"), "--local-replay"]
    if cards:
        args += ["--cards", str(path / "cards.txt")]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=120)


def report(path):
    return json.loads((path / "out/report.json").read_text(encoding="utf-8"))


def test_download_score_keeps_page_and_local_receipts_separate(tmp_path):
    fixture(tmp_path)
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    data = report(tmp_path)
    assert data["passed_checks"] == 4
    assert data["page_card_status"] == "matched_summary_only"
    assert data["native_tool_receipt_verified"] is False
    assert data["reported_exit_code"] is None
    assert data["local_replay"]["opened_files"] == ["movements.csv", "invoices.csv", "fx.csv"]
    assert data["local_replay"]["result_matches_archive"]
    raw = json.loads((tmp_path / "out/local-tool-responses.json").read_text(encoding="utf-8"))
    assert raw["origin"] == "local_replay_not_evo"
    assert [item["status"] for item in raw["calls"]] == ["timeout", "ok", "ok", "ok", "denied"]
    assert raw["calls"][1]["result"][0]["event"] == "001"


def test_correct_business_answer_does_not_cover_wrong_tool_arguments(tmp_path):
    fixture(tmp_path, bad_audit=True)
    assert run(tmp_path, cards=False).returncode == 0
    data = report(tmp_path)
    assert data["passed_checks"] == 3
    assert data["page_card_status"] == "not_provided"
    assert not data["local_replay"]["result_matches_archive"]


def test_wrong_reported_run_is_not_treated_as_verified(tmp_path):
    fixture(tmp_path, receipt_id="r999")
    assert run(tmp_path).returncode == 0
    assert report(tmp_path)["page_card_status"] == "conflict"
    assert report(tmp_path)["native_tool_receipt_verified"] is False


def test_wrong_source_hash_stops_before_creating_output(tmp_path):
    fixture(tmp_path, corrupt_source=True)
    assert run(tmp_path).returncode != 0
    assert not (tmp_path / "out").exists()


def test_archive_cannot_add_an_unexpected_path(tmp_path):
    fixture(tmp_path)
    with zipfile.ZipFile(tmp_path / "result.zip", "a") as archive:
        archive.writestr("run-1/../escape.py", "must not be read or extracted")
    assert run(tmp_path).returncode != 0
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "escape.py").exists()


def test_input_bytes_must_match_independent_freeze(tmp_path):
    fixture(tmp_path)
    path = tmp_path / "result.zip"
    with zipfile.ZipFile(path) as archive:
        items = {name: archive.read(name) for name in archive.namelist()}
    items["run-1/inputs/data/invoices.csv"] += b"CNY,9\n"
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in items.items():
            archive.writestr(name, value)
    assert run(tmp_path).returncode != 0
    assert not (tmp_path / "out").exists()
