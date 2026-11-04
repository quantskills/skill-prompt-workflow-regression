"""Read strict task outputs from official EVO protocol exports.

An abandoned retry is not the final answer. Code fences, prose, duplicate
JSON keys, missing task IDs and non-standard JSON numbers are not repaired.
"""
import json


def final_response(frames: list[dict]) -> str:
    current = []
    final = None
    completed = False
    failed = False
    for frame in frames:
        kind = frame.get("type")
        if kind == "text_delta":
            current.append(frame.get("text", ""))
        elif kind == "assistant_segment_end":
            if frame.get("outcome") == "final":
                final = "".join(current)
            current = []
        elif kind == "error":
            failed = True
        elif kind == "turn_done":
            completed = not frame.get("truncated", False)
    if not completed or failed or final is None:
        raise ValueError("No successfully completed final assistant segment")
    return final


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError("Non-standard JSON number: " + value)


def parse_batch(text: str, expected_ids: set[str]) -> dict[str, str]:
    try:
        data = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_number)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Final response is not strict JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("responses"), list):
        raise ValueError("Missing responses array")
    result = {}
    for row in data["responses"]:
        if not isinstance(row, dict) or not isinstance(row.get("task_id"), str) or not isinstance(row.get("output"), dict):
            raise ValueError("Invalid task response record")
        task_id = row["task_id"]
        if task_id in result:
            raise ValueError("Duplicate task ID")
        result[task_id] = json.dumps(row["output"], ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if set(result) != expected_ids:
        raise ValueError("Missing or unexpected task IDs")
    return result


def verify_session(input_message: dict, frames: list[dict], receipt: dict, project: str, model: str) -> dict:
    """Compare a separately retrieved platform session with its transport export."""
    if receipt.get("projectId") != project:
        raise ValueError("Platform project mismatch")
    if receipt.get("modelId") != model or receipt.get("lastEffectiveModelId") != model:
        raise ValueError("Platform model mismatch")
    timeline = receipt.get("timeline", [])
    users = [row for row in timeline if row.get("role") == "user"]
    answers = [row for row in timeline if row.get("role") == "assistant" and row.get("phase") == "answer"]
    if len(users) != 1 or users[0].get("text") != input_message.get("text"):
        raise ValueError("Platform input mismatch")
    if not answers or answers[-1].get("text", "").strip() != final_response(frames).strip():
        raise ValueError("Platform final response mismatch")
    return {"matched": True, "session": receipt["id"], "input_matches": True, "final_matches": True,
            "canonical_transcript_digest": receipt.get("canonicalTranscriptDigest")}
