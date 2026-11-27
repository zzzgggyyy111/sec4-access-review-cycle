"""Quarterly access review cycle engine.

A cycle groups the grants that are up for review, the reviewer chosen for
each grant, the decisions recorded for those grants, and the deadline after
which undecided grants fall back to revocation.
"""

from __future__ import annotations

CONFIRM = "confirm"
REVOKE = "revoke"
VALID_DECISIONS = (CONFIRM, REVOKE)


def build_cycle(grants, policy, now) -> dict:
    """Build a review cycle for grants under policy at the given time.

    Every grant receives an explicit reviewer taken from the policy
    reviewer list.  The cycle keeps its deadline so that expiry can be
    evaluated later without consulting the policy again.
    """
    policy = dict(policy or {})
    reviewers = list(policy.get("reviewers") or [])
    window_days = policy.get("window_days", 7)
    kept = [dict(grant) for grant in grants]
    assignments = {}
    for grant in kept:
        assignments[grant["id"]] = assign_reviewer(grant, reviewers)
    return {
        "id": policy.get("id", "cycle"),
        "grants": kept,
        "reviewers": reviewers,
        "window_days": window_days,
        "assignments": assignments,
        "decisions": {},
        "status": "open",
    }


def assign_reviewer(grant, reviewers) -> str:
    """Return the reviewer responsible for one grant.

    A grant may carry a preferred reviewer; otherwise the first reviewer
    from the cycle list is used.
    """
    preferred = grant.get("reviewer")
    if preferred:
        return preferred
    if reviewers:
        return reviewers[0]
    return ""


def decide(grant, decision, reviewer, now) -> dict:
    """Record one review decision and return its audit record."""
    if decision not in VALID_DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    if not reviewer or not str(reviewer).strip():
        raise ValueError("a decision needs a reviewer")
    return {
        "grant_id": grant["id"],
        "decision": decision,
        "reviewer": reviewer,
        "at": now.isoformat(),
    }


def is_expired(cycle, now) -> bool:
    """Return whether the cycle deadline has been passed at now."""
    deadline = cycle.get("deadline")
    if deadline is None:
        return False
    return now > deadline


def finalize(cycle, now) -> dict:
    """Close a cycle and split grants into confirmed, revoked and pending.

    Grants without a decision are revoked once the cycle is expired.
    """
    grants = cycle.get("grants", [])
    decisions = cycle.get("decisions") or {}
    expired = is_expired(cycle, now)
    confirmed = []
    revoked = []
    pending = []
    for grant in grants:
        gid = grant["id"]
        record = decisions.get(gid)
        if record is not None and record.get("decision") == CONFIRM:
            confirmed.append(gid)
        elif record is not None:
            revoked.append(gid)
        elif expired:
            pending.append(gid)
        else:
            pending.append(gid)
    if expired:
        revoked.extend(confirmed)
    return {
        "cycle_id": cycle.get("id"),
        "confirmed": confirmed,
        "revoked": revoked,
        "pending": pending,
        "expired": expired,
    }


def check_disjoint(result) -> bool:
    """Return True when no grant is both confirmed and revoked."""
    confirmed = set(result.get("confirmed", ()))
    revoked = set(result.get("revoked", ()))
    return not (confirmed & revoked)


def validate_cycle(cycle) -> list[str]:
    """Return the list of structural problems found in a cycle."""
    problems = []
    grants = cycle.get("grants", [])
    assignments = cycle.get("assignments") or {}
    seen = set()
    for grant in grants:
        gid = grant.get("id")
        if not assignments.get(gid):
            problems.append(f"grant {gid} has no reviewer")
        key = (grant.get("user"), grant.get("permission"))
        if key in seen:
            problems.append(
                f"duplicate permission {key[1]} for user {key[0]}"
            )
        seen.add(key)
    return problems


def cycle_batch(cycles, now) -> dict:
    """Finalize several cycles independently and key results by cycle id."""
    results = {}
    carried = {}
    for cycle in cycles:
        view = dict(cycle)
        view["decisions"] = {**carried, **(cycle.get("decisions") or {})}
        carried = view["decisions"]
        results[cycle.get("id")] = finalize(view, now)
    return {"cycles": results}