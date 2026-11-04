import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from regression import analyze, canonical_hash, evaluate, freeze, update_local_pointer


def fixture(tmp_path):
    tasks=[{"id":str(i),"split":"development" if i<2 else "holdout","input":{"x":i},
            "rules":[{"path":["answer"],"equals":i,"type":"number"}]} for i in range(4)]
    suite={"tasks":tasks,"model":"frozen-test-model","model_parameters":{"temperature":0,"seed":42},
           "evaluator":"deterministic-json-rules-v1","min_repeats":3,"max_cost_ratio":1.2}
    manifest=freeze(suite,tmp_path/"manifest.json")
    versions={"baseline":"v1","candidate":"v2","suite_hash":manifest["suite_hash"],
              "version_hashes":{"v1":canonical_hash("prompt-v1"),"v2":canonical_hash("prompt-v2")}}
    runs=[]
    for task in tasks:
        for version in ("v1","v2"):
            for repeat in range(3):
                runs.append({"run_id":f"{task['id']}-{version}-{repeat}","task_id":task["id"],"version":version,
                             "repeat":repeat,"model":suite["model"],"model_parameters":suite["model_parameters"],
                             "task_hash":manifest["task_hashes"][task["id"]],"version_hash":versions["version_hashes"][version],
                             "platform_run_id":"fixture:offline","status":"completed","response":json.dumps({"answer":int(task["id"])}),
                             "cost":.01,"tokens":100,"latency_seconds":1})
    return suite,manifest,versions,runs


def test_freeze_rejects_mutated_holdout(tmp_path):
    suite,manifest,_,_=fixture(tmp_path)
    suite["tasks"][-1]["input"]["x"]=999
    with pytest.raises(ValueError,match="不能覆盖"):
        freeze(suite,tmp_path/"manifest.json")


def test_repeat_evaluation_and_fixture_not_platform_proof(tmp_path):
    s,m,v,r=fixture(tmp_path); report,_=analyze(s,m,v,r,"holdout")
    assert report["accepted"]
    assert not report["platform_execution_verified"]
    assert not report["platform_record_ids_present"]
    assert report['n_tasks'] == 2
    assert report['interval_scope'] == 'descriptive_task_resampling_not_independent_call_confidence'


def test_regression_detected_and_local_pointer_rolled_back(tmp_path):
    s,m,v,r=fixture(tmp_path)
    for run in r:
        if run["task_id"]=="3" and run["version"]=="v2":
            run["response"]='{"answer": -1}'
    report,_=analyze(s,m,v,r,"holdout")
    assert not report["accepted"]
    state=tmp_path/"state.json"; state.write_text('{"active_version":"v2"}')
    after=update_local_pointer(report,state)
    assert after["active_version"]=="v1" and after["action"]=="rollback"


def test_model_drift_and_missing_repeats_rejected(tmp_path):
    s,m,v,r=fixture(tmp_path); r[-1]["model"]="changed"
    with pytest.raises(ValueError,match="模型"):
        analyze(s,m,v,r,"holdout")
    s,m,v,r=fixture(tmp_path)
    with pytest.raises(ValueError,match="重复次数"):
        analyze(s,m,v,r[:-1],"holdout")


def test_cost_and_development_cannot_trigger_rollout(tmp_path):
    s,m,v,r=fixture(tmp_path)
    for run in r:
        if run["version"]=="v2": run["cost"]*=2
    report,_=analyze(s,m,v,r,"holdout"); assert not report["accepted"]
    dev,_=analyze(s,m,v,r,"development")
    with pytest.raises(ValueError,match="开发集"):
        update_local_pointer(dev,tmp_path/"state.json")


def test_boolean_is_not_number_and_invalid_json_fails():
    assert not evaluate('{"x":true}',[{"path":["x"],"type":"number"}])[0]
    assert not evaluate('not-json',[{"type":"object"}])[0]


@pytest.mark.parametrize("invalid_tokens", [1.5, -0.5, True])
def test_token_counts_cannot_be_silently_coerced(tmp_path, invalid_tokens):
    suite, manifest, versions, runs = fixture(tmp_path)
    runs[-1]["tokens"] = invalid_tokens
    with pytest.raises(ValueError, match="token"):
        analyze(suite, manifest, versions, runs, "holdout")


@pytest.mark.parametrize("response", ['{"x":0,"x":1}', '{"x":NaN}', '{"x":Infinity}'])
def test_direct_run_export_cannot_bypass_strict_json(response):
    assert not evaluate(response, [{"type":"object"}])[0]


def test_one_real_call_cannot_count_as_independent_repeats(tmp_path):
    s,m,v,r=fixture(tmp_path)
    for run in r:
        run["platform_run_id"] = f"actual:{run['version']}"
    with pytest.raises(ValueError,match="独立"):
        analyze(s,m,v,r,"holdout")


def test_batched_call_ids_are_allowed_within_one_repeat(tmp_path):
    s,m,v,r=fixture(tmp_path)
    for run in r:
        run["platform_run_id"] = f"actual:{run['version']}:{run['repeat']}"
    report,_=analyze(s,m,v,r,"holdout")
    assert report["independent_platform_calls"] == 6


def test_actual_cli_evaluates_records_and_rolls_back(tmp_path):
    s,m,v,r=fixture(tmp_path)
    for run in r:
        if run["version"]=="v2":run["response"]='{}'
    for name,obj in (("suite",s),("versions",v)):
        (tmp_path/(name+".json")).write_text(json.dumps(obj),encoding="utf-8")
    (tmp_path/"runs.jsonl").write_text("\n".join(json.dumps(x) for x in r),encoding="utf-8")
    script=Path(__file__).parents[1]/"scripts"/"regression.py"
    args=[sys.executable,"-X","utf8",str(script),"evaluate"]
    for name in ("suite","manifest","versions","runs"):
        args.extend(["--"+name,str(tmp_path/(name+(".jsonl" if name=="runs" else ".json")))])
    args.extend(["--split","holdout","--output",str(tmp_path/"result"),"--local-state",str(tmp_path/"state.json")])
    proc=subprocess.run(args,capture_output=True,text=True,encoding="utf-8")
    assert proc.returncode==0,proc.stderr
    assert json.loads((tmp_path/"state.json").read_text())["active_version"]=="v1"
    before = (tmp_path/"result"/"report.json").read_bytes()
    state_before = (tmp_path/"state.json").read_bytes()
    again = subprocess.run(args,capture_output=True,text=True,encoding="utf-8")
    assert again.returncode != 0, "Repeated runs must not overwrite prior evidence"
    assert (tmp_path/"result"/"report.json").read_bytes() == before
    assert (tmp_path/"state.json").read_bytes() == state_before


def test_equal_failure_is_not_a_release_or_safe_rollback(tmp_path):
    s,m,v,r=fixture(tmp_path)
    for run in r:
        run["response"]='{}'
    report,_=analyze(s,m,v,r,"holdout")
    assert not report["accepted"]
    assert report["recommended_version"] is None
    state=tmp_path/"state.json"
    state.write_text('{"active_version":"v2"}')
    after=update_local_pointer(report,state)
    assert after["action"]=="block"
    assert after["active_version"]=="v2"
    assert not after["approved_for_use"]
