"""Adversarial fixtures: evaluator correctness, not measured model competence."""
import json

import pytest

from regression import analyze, evaluate, freeze, update_local_pointer
from test_regression import fixture


@pytest.mark.parametrize("wrong", [
    {"decision": "sell", "quantity": 10},
    {"decision": "hold", "quantity": 100},
    {"decision": "hold", "quantity": "10"},
])
def test_valid_json_with_wrong_business_answer_fails(wrong):
    expected = {"decision": "hold", "quantity": 10}
    rules = [{"exact_json": expected}]
    assert evaluate(json.dumps(expected), rules)[0]
    assert not evaluate(json.dumps(wrong), rules)[0]


@pytest.mark.parametrize("mutation", [
    {"tool": "place_order"},
    {"arguments": {"symbol": "CL", "limit": 10, "dry_run": True}},
    {"arguments": {"symbol": "SC", "limit": -10, "dry_run": True}},
    {"arguments": {"symbol": "SC", "limit": "10", "dry_run": True}},
    {"arguments": {"symbol": "SC", "limit": 10}},
    {"arguments": {"symbol": "SC", "limit": 10, "dry_run": 1}},
    {"arguments": {"symbol": "SC", "limit": 10, "dry_run": True, "execute": True}},
])
def test_tool_name_arguments_types_and_extra_fields(mutation):
    expected = {"tool": "query_history", "arguments": {"symbol": "SC", "limit": 10, "dry_run": True}}
    rules = [{"exact_json": expected}]
    assert evaluate(json.dumps(expected), rules)[0]
    assert not evaluate(json.dumps(expected | mutation), rules)[0]


@pytest.mark.parametrize("wrong", [
    {"status": "success", "next": "stop", "retry": False},
    {"status": "timeout", "next": "place_order", "retry": True},
    {"status": "timeout", "next": "check_status", "retry": 1},
])
def test_timeout_requires_status_check_not_blind_duplicate_action(wrong):
    expected = {"status": "timeout", "next": "check_status", "retry": False}
    assert evaluate(json.dumps(expected), [{"exact_json": expected}])[0]
    assert not evaluate(json.dumps(wrong), [{"exact_json": expected}])[0]


def test_failed_execution_with_correct_payload_still_rolls_back(tmp_path):
    s, m, v, runs = fixture(tmp_path)
    for row in runs:
        if row["version"] == "v2":
            row["status"] = "failed"
    report, rows = analyze(s, m, v, runs, "holdout")
    assert not report["accepted"]
    assert not rows[rows.version == "v2"].passed.any()
    assert all("execution_failed" in reason for reason in rows[rows.version == "v2"].reasons)
    state = tmp_path / "state.json"
    state.write_text('{"active_version":"v2"}', encoding="utf-8")
    assert update_local_pointer(report, state)["action"] == "rollback"
    for row in runs:
        row["status"] = "completed"
    recovered, _ = analyze(s, m, v, runs, "holdout")
    assert update_local_pointer(recovered, state)["action"] == "promote"


def test_in_progress_execution_cannot_be_used_as_recovered(tmp_path):
    s, m, v, runs = fixture(tmp_path)
    runs[-1]["status"] = "running"
    with pytest.raises(ValueError, match="尚未结束"):
        analyze(s, m, v, runs, "holdout")


def test_unknown_current_version_is_preserved(tmp_path):
    s, m, v, runs = fixture(tmp_path)
    report, _ = analyze(s, m, v, runs, "holdout")
    state = tmp_path / "state.json"
    original = '{"active_version":"unrelated-production-version"}'
    state.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="禁止覆盖"):
        update_local_pointer(report, state)
    assert state.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("rules", [[], [{}], [{"equal": 1}], [{"path": [-1], "equals": 1}]])
def test_invalid_rules_cannot_silently_pass(rules):
    with pytest.raises(ValueError, match="量规"):
        evaluate('{"answer":1}', rules)


def test_new_semantic_rules_require_separate_v2_freeze(tmp_path):
    s, _, _, _ = fixture(tmp_path)
    s["tasks"][0]["rules"] = [{"exact_json": {"steps": [{"retry": False}]}}]
    with pytest.raises(ValueError, match="v2"):
        freeze(s, tmp_path / "new.json")
    s["evaluator"] = "deterministic-json-rules-v2"
    assert freeze(s, tmp_path / "new.json")["evaluator"].endswith("v2")
    assert not evaluate('{"steps":[{"retry":0}]}', s["tasks"][0]["rules"])[0]


@pytest.mark.parametrize("repeat", [True, 1.0, "1", -1])
def test_repeat_identity_cannot_be_coerced(tmp_path, repeat):
    s, m, v, runs = fixture(tmp_path)
    for row in runs:
        if row["repeat"] == 1:
            row["repeat"] = repeat
    with pytest.raises(ValueError, match="重复"):
        analyze(s, m, v, runs, "holdout")


@pytest.mark.parametrize("minimum", [True, 3.5, "3"])
def test_freeze_cannot_truncate_repeat_requirement(tmp_path, minimum):
    s, _, _, _ = fixture(tmp_path)
    s["min_repeats"] = minimum
    with pytest.raises(ValueError, match="重复"):
        freeze(s, tmp_path / "changed.json")
