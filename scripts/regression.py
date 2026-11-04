"""Audit exported EVO runs against a frozen task suite and local release pointer."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from platform_export import _invalid_number, _unique_object


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def freeze(suite: dict, path: Path) -> dict:
    if str(suite.get("status", "")).startswith("draft") or "SELECT_ACTUAL" in str(suite.get("model", "")):
        raise ValueError("草案的实际模型配置未确认，不能冻结")
    if not suite.get("model") or not isinstance(suite.get("model_parameters"), dict):
        raise ValueError("缺少实际模型或参数")
    if not 0 <= float(suite.get("max_pass_rate_drop", 0)) <= 1 or float(suite.get("max_cost_ratio", 1.2)) <= 0:
        raise ValueError("通过率或费用阈值不合法")
    if not 0 <= float(suite.get("min_candidate_pass_rate", .9)) <= 1:
        raise ValueError("最低可用通过率不合法")
    tasks = suite["tasks"]
    ids = [t["id"] for t in tasks]
    if len(set(ids)) != len(ids) or not tasks:
        raise ValueError("任务集为空或任务编号重复")
    if {t["split"] for t in tasks} != {"development", "holdout"}:
        raise ValueError("任务集必须分别包含开发集与保留集")
    for task in tasks:
        if not task.get("rules") or "input" not in task:
            raise ValueError("每个任务必须有输入和冻结量规")
    if suite.get("evaluator") != "deterministic-json-rules-v1":
        raise ValueError("未支持的量规版本")
    manifest = {"suite_hash": canonical_hash(suite), "model": suite["model"],
                "model_parameters": suite["model_parameters"], "evaluator": suite["evaluator"],
                "task_hashes": {t["id"]: canonical_hash(t) for t in tasks}}
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("冻结清单已存在且内容改变；请建立新研究版本，不能覆盖保留集")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def evaluate(response: str, rules: list[dict]) -> tuple[bool, list[str]]:
    try:
        obj = json.loads(response, object_pairs_hook=_unique_object, parse_constant=_invalid_number)
        json.dumps(obj, allow_nan=False)
    except (ValueError, TypeError):
        return False, ["invalid_json"]
    reasons = []
    types = {"object": dict, "array": list, "string": str, "number": (int, float), "boolean": bool}
    for rule in rules:
        value = obj
        try:
            for key in rule.get("path", []):
                value = value[key]
        except (KeyError, TypeError, IndexError):
            reasons.append("missing_path:"+str(rule.get("path"))); continue
        if "equals" in rule and value != rule["equals"]:
            reasons.append("wrong_value:"+str(rule.get("path")))
        if "type" in rule:
            if rule["type"] not in types:
                raise ValueError("未知量规类型")
            valid = isinstance(value, types[rule["type"]])
            if rule["type"] == "number" and isinstance(value, bool):
                valid = False
            if not valid:
                reasons.append("wrong_type:"+str(rule.get("path")))
        if "contains" in rule and (not isinstance(value, (str, list, dict)) or rule["contains"] not in value):
            reasons.append("missing_content:"+str(rule.get("path")))
    return not reasons, reasons


def analyze(suite: dict, manifest: dict, versions: dict, runs: list[dict], split: str) -> tuple[dict, pd.DataFrame]:
    if manifest["suite_hash"] != canonical_hash(suite):
        raise ValueError("任务集与冻结清单不符")
    baseline, candidate = versions["baseline"], versions["candidate"]
    if baseline == candidate:
        raise ValueError("基线和候选版本不能相同")
    if versions.get("suite_hash") != manifest["suite_hash"]:
        raise ValueError("版本选择未绑定冻结任务集")
    tasks = {t["id"]: t for t in suite["tasks"] if t["split"] == split}
    records, seen = [], set()
    for run in runs:
        if run["run_id"] in seen:
            raise ValueError("运行编号重复")
        seen.add(run["run_id"])
        if run["task_id"] not in tasks:
            continue
        if run["version"] not in (baseline, candidate):
            continue
        if run["model"] != manifest["model"] or run["model_parameters"] != manifest["model_parameters"]:
            raise ValueError("模型或采样参数漂移，不能直接比较")
        if run.get("task_hash") != manifest["task_hashes"][run["task_id"]]:
            raise ValueError("运行输入或量规与冻结任务不符")
        expected = versions["version_hashes"][run["version"]]
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("版本标识必须是完整 SHA256")
        if run.get("version_hash") != expected:
            raise ValueError("提示词或工作流版本散列不一致")
        if not run.get("platform_run_id"):
            raise ValueError("缺少 EVO 运行标识；本地样例必须明确使用 fixture 标识")
        if run.get("status") not in ("completed", "failed"):
            raise ValueError("运行尚未结束，不能计入完成记录")
        tokens = run["tokens"]
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise ValueError("token 数量必须为非负整数，不接受隐式取整")
        cost = float(run["cost"]); latency = float(run["latency_seconds"])
        if not np.isfinite([cost, latency]).all() or min(cost, tokens, latency) < 0:
            raise ValueError("费用、token 或延迟不合法")
        ok, reasons = evaluate(run.get("response", ""), tasks[run["task_id"]]["rules"])
        ok = ok and run["status"] == "completed"
        records.append({"task_id": run["task_id"], "version": run["version"], "repeat": run["repeat"],
                        "passed": ok, "reasons": json.dumps(reasons), "cost": cost, "tokens": tokens,
                        "latency_seconds": latency, "platform_run_id": run["platform_run_id"]})
    df = pd.DataFrame(records)
    if df.empty or df.duplicated(["task_id", "version", "repeat"]).any():
        raise ValueError("没有运行记录或重复实验键冲突")
    calls = {}
    for row in records:
        call_id = str(row["platform_run_id"])
        if call_id.startswith("fixture:"):
            continue
        owner = (row["version"], row["repeat"])
        if call_id in calls and calls[call_id] != owner:
            raise ValueError("同一平台调用被复用为独立重复或不同版本")
        calls[call_id] = owner
    minimum = int(suite.get("min_repeats", 3))
    if minimum < 3:
        raise ValueError("稳定性研究至少重复三次")
    repeats = set(range(minimum))
    for task_id in tasks:
        for version in (baseline, candidate):
            actual = set(df.loc[(df.task_id == task_id) & (df.version == version), "repeat"])
            if actual != repeats:
                raise ValueError(f"{task_id}/{version} 重复次数不完整或不匹配")
    per_task = df.groupby(["task_id", "version"]).passed.mean().unstack("version")
    delta = (per_task[candidate]-per_task[baseline]).to_numpy(float)
    rng = np.random.default_rng(42)
    bootstrap = rng.choice(delta, size=(2000, len(delta)), replace=True).mean(1)
    stats = {}
    for version in (baseline, candidate):
        part = df[df.version == version]
        by_repeat = part.groupby("repeat").passed.mean()
        stats[version] = {"pass_rate": float(part.passed.mean()), "repeat_pass_rate_std": float(by_repeat.std(ddof=0)),
                          "total_cost": float(part.cost.sum()), "total_tokens": int(part.tokens.sum()),
                          "median_latency_seconds": float(part.latency_seconds.median())}
    cost_ratio = stats[candidate]["total_cost"]/max(stats[baseline]["total_cost"], 1e-12)
    margin = float(suite.get("max_pass_rate_drop", 0))
    minimum_quality = float(suite.get("min_candidate_pass_rate", .9))
    accepted = bool(stats[candidate]["pass_rate"] >= minimum_quality
                    and delta.mean() >= -margin and np.quantile(bootstrap, .025) >= -margin
                    and cost_ratio <= float(suite.get("max_cost_ratio", 1.2)))
    recommended = candidate if accepted else baseline if stats[baseline]["pass_rate"] >= minimum_quality else None
    verified_ids = all(not str(r["platform_run_id"]).startswith("fixture:") for r in records)
    report = {"suite_hash": manifest["suite_hash"], "split": split, "baseline": baseline, "candidate": candidate,
              "statistics": stats, "paired_task_pass_rate_delta": float(delta.mean()),
              "paired_bootstrap_95pct_interval": np.quantile(bootstrap, [.025,.975]).tolist(),
              "n_tasks": len(delta),
              "interval_scope": "descriptive_task_resampling_not_independent_call_confidence",
              "cost_ratio": cost_ratio, "minimum_pass_rate": minimum_quality,
              "accepted": accepted, "recommended_version": recommended,
              "approved_version_available": recommended is not None,
              "platform_record_ids_present": verified_ids,
              "independent_platform_calls": len(calls),
              "platform_execution_verified": False,
              "evidence_note": "Exported identifiers require independent platform log verification."}
    return report, df


def update_local_pointer(report: dict, state_path: Path) -> dict:
    if report["split"] != "holdout":
        raise ValueError("开发集不能触发发布或回滚")
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"active_version": report["baseline"]}
    if previous["active_version"] not in (report["baseline"], report["candidate"]):
        raise ValueError("当前版本不属于本次冻结比较，禁止覆盖")
    approved = report["recommended_version"] is not None
    state = {"active_version": report["recommended_version"] if approved else previous["active_version"], "previous_version": previous["active_version"],
             "action": "block" if not approved else "promote" if report["accepted"] else "rollback",
             "approved_for_use": approved, "suite_hash": report["suite_hash"],
             "scope": "local_pointer_only_platform_rollout_requires_real_run"}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(state_path)
    return state


def main() -> None:
    p = argparse.ArgumentParser(description="EVO 提示词与工作流稳定性、退化检测和回滚核验")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--suite", required=True); f.add_argument("--manifest", required=True)
    e = sub.add_parser("evaluate")
    for field in ("suite", "manifest", "versions", "runs", "output"):
        e.add_argument("--"+field, required=True)
    e.add_argument("--split", choices=["development","holdout"], required=True)
    e.add_argument("--local-state")
    a = p.parse_args(); suite = json.loads(Path(a.suite).read_text(encoding="utf-8"))
    if a.command == "freeze":
        print(json.dumps(freeze(suite, Path(a.manifest)), ensure_ascii=False)); return
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    versions = json.loads(Path(a.versions).read_text(encoding="utf-8"))
    runs = [json.loads(line) for line in Path(a.runs).read_text(encoding="utf-8").splitlines() if line.strip()]
    report, rows = analyze(suite, manifest, versions, runs, a.split)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    (out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows.to_csv(out/"run_scores.csv", index=False)
    if a.local_state:
        update_local_pointer(report, Path(a.local_state))
    print(json.dumps({"accepted": report["accepted"], "recommended_version": report["recommended_version"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
