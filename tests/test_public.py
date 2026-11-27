from datetime import datetime, timedelta

import pytest

from engine.rev.cycle import (
    assign_reviewer,
    build_cycle,
    cycle_batch,
    decide,
    finalize,
)

NOW = datetime(2026, 1, 15, 9, 0, 0)
POLICY = {"id": "c1", "window_days": 7, "reviewers": ["alice", "bob"]}


def make_grant(gid, user="u1", permission="read"):
    return {"id": gid, "user": user, "permission": permission}


def test_build_cycle_assigns_reviewers_and_deadline():
    grants = [make_grant("g1"), make_grant("g2", permission="write")]
    cycle = build_cycle(grants, POLICY, NOW)

    assert cycle["id"] == "c1"
    assert [grant["id"] for grant in cycle["grants"]] == ["g1", "g2"]
    assert cycle["deadline"] == NOW + timedelta(days=7)
    assert cycle["assignments"] == {"g1": "alice", "g2": "alice"}
    assert cycle["status"] == "open"


def test_assign_reviewer_rejects_empty_reviewer_pool():
    with pytest.raises(ValueError):
        assign_reviewer(make_grant("g1"), [])


def test_confirm_decision_is_kept_in_finalize_trail():
    cycle = build_cycle([make_grant("g1")], POLICY, NOW)
    record = decide(make_grant("g1"), "confirm", "alice", NOW)
    cycle["decisions"]["g1"] = record

    result = finalize(cycle, NOW + timedelta(days=1))

    assert result["confirmed"] == ["g1"]
    assert result["revoked"] == []
    assert result["trail"] == [record]


def test_expired_undecided_grant_is_revoked():
    policy = dict(POLICY, window_days=0)
    cycle = build_cycle([make_grant("g1")], policy, NOW)

    result = finalize(cycle, NOW)

    assert result["revoked"] == ["g1"]
    assert result["confirmed"] == []


def test_batch_cycles_are_independent():
    first = build_cycle([make_grant("g1", user="u1")], dict(POLICY, id="c1"), NOW)
    second = build_cycle(
        [make_grant("g1", user="u2", permission="write")],
        dict(POLICY, id="c2"),
        NOW,
    )
    first["decisions"]["g1"] = decide(make_grant("g1"), "confirm", "alice", NOW)

    batch = cycle_batch([first, second], NOW)

    assert batch["cycles"]["c1"]["confirmed"] == ["g1"]
    assert batch["cycles"]["c2"]["confirmed"] == []
    assert batch["cycles"]["c2"]["pending"] == ["g1"]