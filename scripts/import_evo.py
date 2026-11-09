"""Import a saved, single-turn EVO batch protocol and optional session readback."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from platform_export import _invalid_number, _unique_object, final_response, parse_batch
from regression import canonical_hash, minimum_repeats


DEFAULT_PREFIX = "你在执行冻结的量化输入校验任务。不调用工具，不创建子代理。任务输入列表："
SEPARATOR = "\n\n当前版本指令：\n"


def strict(text):
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_number)


def read(path):
    return strict(path.read_text(encoding="utf-8"))


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("Invalid file or version identifier")
    return value


def digest(raw):
    return sha256(raw).hexdigest()


def local_file(directory, name):
    path = (directory / name).resolve()
    if path.parent != directory.resolve():
        raise ValueError("Evidence path leaves its configured directory")
    return path


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Usage or duration must be finite and nonnegative")
    return value


def request_text(tasks, prompt, prefix):
    items = [{"task_id": task["id"], "input": task["input"]} for task in tasks]
    return prefix + "\n" + json.dumps(items, ensure_ascii=False, indent=2, allow_nan=False) + SEPARATOR + prompt.strip() + "\n"


def one(items, kind):
    matches = [item for item in items if item["type"] == kind]
    if len(matches) != 1:
        raise ValueError("Expected exactly one " + kind)
    return matches[0]


def read_protocol(path, session, project, model, params, expected_request):
    raw = path.read_bytes()
    messages = {"input": [], "output": []}
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            row = strict(line)
            messages[row["direction"]].append(row["message"])
    if len(messages["input"]) != 1:
        raise ValueError("Only one user message per session is supported")
    user = one(messages["input"], "user_message")
    turn = safe_id(user["turn_id"])
    if (user["text"] != expected_request or user["modelId"] != model
            or canonical_hash(user["modelParameters"]["parameters"]) != canonical_hash(params)
            or user.get("references") or user.get("images")):
        raise ValueError("Wire request does not match frozen tasks, prompt or model options")
    frames = messages["output"]
    for frame in frames:
        if frame.get("session_id", session) != session or frame.get("turn_id", turn) != turn:
            raise ValueError("Wire event belongs to a different session or turn")
    started = one(frames, "session_start")
    if started["session_id"] != session or started["project_id"] != project or started["model_id"] != model:
        raise ValueError("Wire project, session or model mismatch")
    applied = one(frames, "model_effective_options")
    actual_options = {key: value["value"] for key, value in applied["effectiveOptions"].items()}
    if applied["effectiveModelId"] != model or canonical_hash(actual_options) != canonical_hash(params):
        raise ValueError("Platform effective model or options drift")
    done = one(frames, "turn_done")
    if done["session_id"] != session or done["turn_id"] != turn:
        raise ValueError("Terminal event identity mismatch")
    end = frames.index(done)
    if not frames.index(started) < frames.index(applied) < end or any(
        frame["type"] in ("text_delta", "assistant_segment_end", "error") for frame in frames[end+1:]
    ):
        raise ValueError("Invalid event order around terminal event")
    cost = number(done["cost"]["usd"])
    tokens = number(done["cost"]["tokens"])
    if type(tokens) is not int:
        raise ValueError("Platform token count must be an integer")
    failed = bool(done.get("truncated", False)) or any(frame["type"] == "error" for frame in frames)
    final = None
    if not failed:
        one([f for f in frames if f.get("outcome") == "final"], "assistant_segment_end")
        final = final_response(frames)
    return user, turn, final, cost, tokens, digest(raw)


def check_receipt(path, session, turn, project, model, user, final):
    if path is None:
        return "not_provided", None
    if not path.exists():
        return "not_found", None
    raw = path.read_bytes()
    receipt = strict(raw.decode("utf-8"))
    users = [row for row in receipt["timeline"] if row["role"] == "user"]
    if (receipt["id"] != session or receipt["projectId"] != project
            or receipt["modelId"] != model or receipt["lastEffectiveModelId"] != model
            or len(users) != 1 or users[0]["turnId"] != turn or users[0]["text"] != user["text"]):
        raise ValueError("Session readback identity or input conflicts with wire record")
    if final is None:
        return "input_matched_final_unverified", digest(raw)
    answers = [row for row in receipt["timeline"] if row["role"] == "assistant" and row.get("phase") == "answer"]
    if not answers or answers[-1]["text"] != final:
        raise ValueError("Session readback final answer differs from wire record")
    return "matched", digest(raw)


def import_evo(args):
    if args.output.exists():
        raise ValueError("Output already exists; choose a new directory")
    suite, manifest, versions = map(read, (args.suite, args.manifest, args.versions))
    tasks = [task for task in suite["tasks"] if task["split"] == args.split]
    task_ids = {task["id"] for task in tasks}
    model, params = suite["model"], suite["model_parameters"]
    suite_hash = canonical_hash(suite)
    if (not tasks or len(task_ids) != len(tasks) or manifest["suite_hash"] != suite_hash
            or versions["suite_hash"] != suite_hash or manifest["model"] != model
            or manifest["model_parameters"] != params or manifest["evaluator"] != suite["evaluator"]
            or any(manifest["task_hashes"][t["id"]] != canonical_hash(t) for t in tasks)):
        raise ValueError("Task, model or suite freeze mismatch")
    selected = {safe_id(versions["baseline"]), safe_id(versions["candidate"])}
    if len(selected) != 2:
        raise ValueError("Choose two distinct frozen versions")
    requests = {}
    for version in selected:
        raw = local_file(args.prompts_dir, version + ".txt").read_bytes()
        if digest(raw) != versions["version_hashes"][version]:
            raise ValueError("Prompt bytes do not match the frozen version")
        requests[version] = request_text(tasks, raw.decode("utf-8"), args.request_prefix)
    if len(set(requests.values())) != 2:
        raise ValueError("Frozen requests are indistinguishable in this format")
    expected = {(version, n) for version in selected for n in range(minimum_repeats(suite))}
    seen, sessions, turns, files = set(), set(), set(), set()
    runs, batches = [], []
    index = read(args.index)
    if not isinstance(index, list):
        raise ValueError("The batch index must be a JSON array")
    for batch in index:
        version, repeat = batch["version"], batch["repeat"]
        key = (version, repeat)
        session = safe_id(batch["session_id"])
        name = batch["protocol_file"]
        if not isinstance(name, str) or not name.endswith(".jsonl"):
            raise ValueError("Protocol filename must end in .jsonl")
        safe_id(name[:-6])
        if type(repeat) is not int or key not in expected or key in seen or session in sessions or name.casefold() in files:
            raise ValueError("Unknown or reused version, repeat, session or file")
        seen.add(key)
        sessions.add(session)
        files.add(name.casefold())
        elapsed = number(batch["elapsed_seconds"])
        user, turn, final, cost, tokens, raw_hash = read_protocol(
            local_file(args.protocol_dir, name), session, args.project, model, params, requests[version]
        )
        if turn in turns:
            raise ValueError("Reused platform turn")
        turns.add(turn)
        receipt = local_file(args.receipts_dir, session + ".json") if args.receipts_dir else None
        receipt_status, receipt_hash = check_receipt(receipt, session, turn, args.project, model, user, final)
        outputs, output_status = {}, "platform_failed"
        if final is not None:
            try:
                outputs = parse_batch(final, task_ids)
                output_status = "normalized"
            except ValueError:
                output_status = "invalid_batch_not_repaired"
        count = len(tasks)
        for i, task in enumerate(tasks):
            task_id = task["id"]
            runs.append(dict(run_id=turn + ":" + task_id, task_id=task_id, version=version, repeat=repeat,
                model=model, model_parameters=params, task_hash=manifest["task_hashes"][task_id],
                version_hash=versions["version_hashes"][version], platform_run_id=turn,
                status="failed" if final is None else "completed", response=outputs.get(task_id, ""),
                cost=cost/count, tokens=tokens//count + int(i < tokens % count),
                latency_seconds=elapsed, batch_session=session, raw_protocol_sha256=raw_hash))
        batches.append(dict(version=version, repeat=repeat, platform_run_id=turn, session_id=session,
            receipt_status=receipt_status, receipt_sha256=receipt_hash, raw_protocol_sha256=raw_hash,
            final_response_sha256=digest(final.encode("utf-8")) if final is not None else None,
            output_status=output_status, cost_usd=cost, tokens=tokens, elapsed_seconds=elapsed))
    if seen != expected:
        raise ValueError("Missing frozen repeats; do not backfill them with copied calls")
    audit = dict(format="evo_single_turn_batch_protocol", split=args.split, platform_calls=len(batches),
        task_records=len(runs), session_receipts_matched=sum(b["receipt_status"] == "matched" for b in batches),
        native_tool_receipts_verified=False, batches=batches)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in (("suite.json", suite), ("manifest.json", manifest), ("versions.json", versions),
                       ("evo-import-audit.json", audit)):
        (args.output/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (args.output/"runs.jsonl").open("x", encoding="utf-8") as stream:
        for row in runs:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    return {key: value for key, value in audit.items() if key != "batches"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("suite", "manifest", "versions", "index", "protocol-dir", "prompts-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--receipts-dir", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--split", choices=("development", "holdout"), required=True)
    parser.add_argument("--request-prefix", default=DEFAULT_PREFIX)
    args = parser.parse_args()
    try:
        print(json.dumps(import_evo(args), ensure_ascii=False))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, OverflowError) as exc:
        # Never echo raw platform messages, paths, account metadata or tokens.
        parser.exit(2, f"导入未完成（{type(exc).__name__}）。请核对任务冻结、运行索引、原始日志和回读文件。\n")


if __name__ == "__main__":
    main()
