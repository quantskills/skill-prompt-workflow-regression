"""Prepare this bundled teaching fixture. Not a platform export adapter."""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

from regression import canonical_hash, freeze


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_versions(manifest):
    baseline, candidate = "baseline", "short"
    return {
        "baseline": baseline,
        "candidate": candidate,
        "suite_hash": manifest["suite_hash"],
        "version_hashes": {
            name: canonical_hash(read_json(HERE / "versions" / f"{name}.json"))
            for name in (baseline, candidate)
        },
    }


def lock(suite, work):
    work.mkdir(parents=True, exist_ok=False)
    (work / "suite.json").write_bytes((HERE / "suite.json").read_bytes())
    manifest = freeze(suite, work / "manifest.json")
    (work / "versions.json").write_text(
        json.dumps(frozen_versions(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def pack(suite, work):
    manifest = read_json(work / "manifest.json")
    versions = read_json(work / "versions.json")
    if read_json(work / "suite.json") != suite or manifest["suite_hash"] != canonical_hash(suite):
        raise ValueError("样例任务与冻结文件不一致")
    if versions != frozen_versions(manifest):
        raise ValueError("样例版本定义与冻结文件不一致")
    tasks = {task["id"]: task for task in suite["tasks"]}
    rows = []
    for line in (HERE / "raw-runs.jsonl").read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        task = tasks[raw["task"]]
        version = raw["variant"]
        if not raw["id"].startswith("fixture:"):
            raise ValueError("此脚本只处理随包提供的离线样例")
        if raw["input"] != task["input"] or manifest["task_hashes"][task["id"]] != canonical_hash(task):
            raise ValueError("样例输入与冻结任务不一致")
        rows.append({
            "run_id": raw["id"],
            "task_id": task["id"],
            "version": version,
            "repeat": raw["attempt"],
            "model": raw["model"],
            "model_parameters": raw["parameters"],
            "task_hash": manifest["task_hashes"][task["id"]],
            "version_hash": versions["version_hashes"][version],
            "platform_run_id": raw["id"],
            "status": raw["state"],
            "response": raw["final_text"],
            "cost": raw["usage"]["cost"],
            "tokens": raw["usage"]["total_tokens"],
            "latency_seconds": raw["elapsed_seconds"],
        })
    with (work / "runs.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("lock", "pack"))
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    suite = read_json(HERE / "suite.json")
    (lock if args.step == "lock" else pack)(suite, args.work_dir)
