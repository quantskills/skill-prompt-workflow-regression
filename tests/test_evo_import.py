import json
from pathlib import Path
import subprocess
import sys

import pytest

from regression import freeze
from hashlib import sha256


SCRIPT = Path(__file__).parents[1] / "scripts" / "import_evo.py"
PREFIX = "你在执行冻结的量化输入校验任务。不调用工具，不创建子代理。任务输入列表："


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    for name in ("wire", "receipts", "prompts"):
        (root / name).mkdir()
    tasks = [
        dict(id=key, split=split, input={"quantity": 2}, rules=[{"path": ["answer"], "equals": 2}])
        for key, split in (("dev", "development"), ("a", "holdout"), ("b", "holdout"))
    ]
    suite = dict(tasks=tasks, model="test-model", model_parameters={"output.max_tokens": 128},
                 evaluator="deterministic-json-rules-v1")
    put(root / "suite.json", suite)
    manifest = freeze(suite, root / "manifest.json")
    prompt_hashes = {}
    index = []
    for version in ("old", "new"):
        prompt = f"{version} instructions\n"
        (root / "prompts" / f"{version}.txt").write_bytes(prompt.encode())
        prompt_hashes[version] = sha256(prompt.encode()).hexdigest()
        input_text = PREFIX + "\n" + json.dumps(
            [{"task_id": t["id"], "input": t["input"]} for t in tasks[1:]], ensure_ascii=False, indent=2
        ) + "\n\n当前版本指令：\n" + prompt
        for repeat in range(3):
            session = f"{version}-{repeat}"
            turn = f"turn-{session}"
            index.append(dict(session_id=session, protocol_file=f"{session}.jsonl", version=version,
                              repeat=repeat, elapsed_seconds=1.5))
            response = '{"responses":[{"task_id":"a","output":{"answer":2}},{"task_id":"b","output":{"answer":2}}]}' if version == "new" else 'text outside JSON'
            user = dict(type="user_message", turn_id=turn, text=input_text, references=[], images=[],
                        modelId=suite["model"], modelParameters={"parameters": suite["model_parameters"]})
            frames = [
                dict(type="session_start", project_id="test-project", model_id=suite["model"]),
                dict(type="model_effective_options", effectiveModelId=suite["model"],
                     effectiveOptions={"output.max_tokens": {"value": 128}}),
                dict(type="text_delta", text="discard me"),
                dict(type="assistant_segment_end", outcome="retry"),
                dict(type="text_delta", text=response),
                dict(type="assistant_segment_end", outcome="final"),
                dict(type="turn_done", cost={"tokens": 7, "usd": .003}),
            ]
            records = [dict(direction="input", message=user)] + [
                dict(direction="output", message={**f, "turn_id": turn, "session_id": session}) for f in frames
            ]
            (root / "wire" / f"{session}.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8"
            )
            put(root / "receipts" / f"{session}.json", {
                "id": session, "projectId": "test-project", "modelId": suite["model"],
                "lastEffectiveModelId": suite["model"],
                "timeline": [{"role": "user", "text": input_text, "turnId": turn},
                             {"role": "assistant", "phase": "answer", "text": response}],
            })
    put(root / "versions.json", dict(baseline="old", candidate="new", suite_hash=manifest["suite_hash"],
                                     version_hashes=prompt_hashes))
    put(root / "index.json", index)
    return root


def run(root, receipts=True):
    args = [sys.executable, "-X", "utf8", str(SCRIPT), "--project", "test-project",
            "--suite", str(root / "suite.json"), "--manifest", str(root / "manifest.json"),
            "--versions", str(root / "versions.json"), "--index", str(root / "index.json"),
            "--protocol-dir", str(root / "wire"), "--prompts-dir", str(root / "prompts"),
            "--split", "holdout", "--output", str(root / "out")]
    if receipts:
        args += ["--receipts-dir", str(root / "receipts")]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=120)


def test_import_preserves_failed_formats_and_conserves_usage(evidence):
    result = run(evidence)
    assert result.returncode == 0, result.stderr
    out = evidence / "out"
    audit = json.loads((out / "evo-import-audit.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 12 and len({row["platform_run_id"] for row in rows}) == 6
    assert sum(row["tokens"] for row in rows) == 42
    assert sum(row["cost"] for row in rows) == pytest.approx(.018)
    assert {row["status"] for row in rows} == {"completed"}
    assert all(not row["response"] for row in rows if row["version"] == "old")
    assert audit["session_receipts_matched"] == 6
    assert audit["native_tool_receipts_verified"] is False
    assert run(evidence).returncode != 0


def test_import_labels_missing_readback(evidence):
    assert run(evidence, receipts=False).returncode == 0
    audit = json.loads((evidence / "out/evo-import-audit.json").read_text(encoding="utf-8"))
    assert audit["session_receipts_matched"] == 0
    assert all(batch["receipt_status"] == "not_provided" for batch in audit["batches"])


@pytest.mark.parametrize("field,value", [("id", "other"), ("lastEffectiveModelId", "other")])
def test_receipt_conflict_does_not_create_output(evidence, field, value):
    path = evidence / "receipts/new-0.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = value
    put(path, data)
    assert run(evidence).returncode != 0
    assert not (evidence / "out").exists()


@pytest.mark.parametrize("change", ["extra_space", "option", "duplicate_call", "missing_usage", "outside_path"])
def test_inconsistent_evidence_is_rejected_without_echoing_text(evidence, change):
    if change == "extra_space":
        path = evidence / "receipts/new-0.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["timeline"][-1]["text"] += " "
        put(path, data)
    elif change in ("duplicate_call", "outside_path"):
        path = evidence / "index.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data[0]["protocol_file"] = data[1]["protocol_file"] if change == "duplicate_call" else "../other.jsonl"
        put(path, data)
    else:
        path = evidence / "wire/new-0.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if change == "option":
            next(r for r in rows if r["message"]["type"] == "model_effective_options")["message"]["effectiveOptions"]["output.max_tokens"]["value"] = 127
        else:
            del rows[-1]["message"]["cost"]["tokens"]
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    result = run(evidence)
    assert result.returncode != 0
    assert "instructions" not in result.stderr and "answer" not in result.stderr
    assert not (evidence / "out").exists()


def test_failed_turn_retains_usage_without_certifying_its_final_answer(evidence):
    path = evidence / "wire/new-0.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[-1]["message"]["truncated"] = True
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert run(evidence).returncode == 0
    audit = json.loads((evidence / "out/evo-import-audit.json").read_text(encoding="utf-8"))
    batch = next(b for b in audit["batches"] if b["session_id"] == "new-0")
    assert batch["output_status"] == "platform_failed"
    assert batch["receipt_status"] == "input_matched_final_unverified"
    assert batch["tokens"] == 7
