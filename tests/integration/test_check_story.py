"""scripts/check_story.py against the mock gateway's replay (the order Kamal builds the UI from), and that it catches
a story told out of order."""
import copy
import importlib.util
import io
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("check_story", Path(__file__).resolve().parents[2] / "scripts" / "check_story.py")
check_story = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_story)


@pytest.fixture(scope="module")
def replay():
    return check_story.mock_events()


def test_the_mock_replay_tells_the_story_in_order(replay):
    out = io.StringIO()
    assert check_story.report(replay, out)
    lines = out.getvalue().splitlines()
    assert lines[-1].startswith("PASS  story order")
    assert any("task.understood" in line for line in lines) and any("task.data" in line for line in lines)


def _move(events, pick, after_type):
    """The event `pick` selects, moved to just after the first event of type after_type."""
    evs = copy.deepcopy(events)
    ev = evs.pop(next(i for i, e in enumerate(evs) if pick(e)))
    evs.insert(next(i for i, e in enumerate(evs) if e["type"] == after_type) + 1, ev)
    return evs


def test_it_catches_a_story_out_of_order(replay):
    understood_late = _move(replay, lambda e: e["type"] == "task.understood", "agent.created")
    assert any("task.understood before agent.planned" in p for p in check_story.check(understood_late))

    data_first = _move(replay, lambda e: e["type"] == "tool.query", "task.data")
    assert any("followed by its task.data" in p for p in check_story.check(data_first))

    synth_early = _move(replay, lambda e: e["type"] == "agent.thought" and e["payload"]["step"] == "synthesize",
                        "approval.requested")
    assert any("synthesis thought" in p for p in check_story.check(synth_early))

    wrong_pid = copy.deepcopy(replay)
    next(e for e in wrong_pid if e["type"] == "agent.thought")["payload"]["pid"] = 999
    assert "thoughts carry their own pid" in check_story.check(wrong_pid)

    out = io.StringIO()
    assert not check_story.report(understood_late, out) and out.getvalue().splitlines()[-1].startswith("FAIL  story order:")
