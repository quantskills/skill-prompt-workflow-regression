import importlib.util
from pathlib import Path
import pytest


def module():
    path = Path(__file__).parents[1] / "scripts/platform_export.py"
    spec = importlib.util.spec_from_file_location("platform_export", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_final_answer_excludes_abandoned_retry():
    frames = [{"type": "text_delta", "text": '{"old":true}'},
              {"type": "assistant_segment_end", "outcome": "retry"},
              {"type": "text_delta", "text": '{"responses":[{"task_id":"a","output":{"quantity":1}}]}'},
              {"type": "assistant_segment_end", "outcome": "final"}, {"type": "turn_done"}]
    m = module()
    assert m.parse_batch(m.final_response(frames), {"a"}) == {"a": '{"quantity":1}'}


def test_code_fence_is_not_silently_repaired():
    m = module()
    with pytest.raises(ValueError):
        m.parse_batch('```json\n{"responses":[]}\n```', set())


@pytest.mark.parametrize("text", [
    '{"responses":[{"task_id":"a","output":{}},{"task_id":"a","output":{}}]}',
    '{"responses":[{"task_id":"b","output":{}}]}',
    '{"responses":[{"task_id":"a","output":{"quantity":NaN}}]}',
    '{"responses":[{"task_id":"a","output":{},"output":{"quantity":1}}]}',
])
def test_ambiguous_or_incomplete_batches_fail(text):
    with pytest.raises(ValueError):
        module().parse_batch(text, {"a"})


def test_unfinished_or_failed_turn_has_no_valid_final_output():
    with pytest.raises(ValueError):
        module().final_response([{"type":"text_delta","text":"{}"}])
    with pytest.raises(ValueError):
        module().final_response([{"type":"error","error":"failed"},{"type":"turn_done"}])


def receipt_fixture():
    frames=[{"type":"text_delta","text":"{}"},{"type":"assistant_segment_end","outcome":"final"},{"type":"turn_done"}]
    receipt={"id":"session-a","projectId":"project-a","modelId":"model-a","lastEffectiveModelId":"model-a",
             "timeline":[{"role":"user","text":"frozen input"},{"role":"assistant","phase":"answer","text":"{}"}]}
    return frames,receipt


def test_saved_platform_session_matches_transport_export():
    frames,receipt=receipt_fixture()
    result=module().verify_session({"text":"frozen input"},frames,receipt,"project-a","model-a")
    assert result["matched"] and result["session"]=="session-a"


@pytest.mark.parametrize("field,value",[("modelId","other-model"),("projectId","other-project")])
def test_wrong_platform_binding_rejected(field,value):
    frames,receipt=receipt_fixture(); receipt[field]=value
    with pytest.raises(ValueError):
        module().verify_session({"text":"frozen input"},frames,receipt,"project-a","model-a")


def test_retrieved_response_mismatch_rejected():
    frames,receipt=receipt_fixture();receipt["timeline"][-1]["text"]='{"changed":true}'
    with pytest.raises(ValueError):
        module().verify_session({"text":"frozen input"},frames,receipt,"project-a","model-a")
