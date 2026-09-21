"""Fail-closed approval policy for the reviewed commit, independent of the model."""
from shared.gitlab import api, pages


def validate_decision(review):
    if review.get("decision") not in ("approve", "unapprove", "abstain"):
        raise ValueError("Review must contain an explicit approval decision")
    if not isinstance(review.get("decision_reason"), str) or not review["decision_reason"].strip():
        raise ValueError("Review must explain its approval decision")


def pipeline_jobs(host, mr):
    pipeline = mr.get("head_pipeline") or {}
    if not pipeline.get("id") or not pipeline.get("project_id"):
        return []
    return pages(host, f"projects/{pipeline['project_id']}/pipelines/{pipeline['id']}/jobs")


def blockers(review, mr, discussions, jobs, head):
    validate_decision(review)
    reasons = []
    if review["decision"] != "approve":
        reasons.append("Codex did not recommend approval: " + review["decision_reason"])
    if review["findings"]:
        reasons.append("The review contains actionable findings")
    if mr.get("state") != "opened" or (mr.get("diff_refs") or {}).get("head_sha") != head:
        reasons.append("The MR is no longer open at the reviewed commit")
    if mr.get("draft") is not False or mr.get("work_in_progress") is True:
        reasons.append("The MR is draft or its draft status is unknown")
    if mr.get("has_conflicts") is not False:
        reasons.append("Merge conflicts exist or their status is unknown")
    # Missing approvals must not prevent this reviewer from adding its approval.
    if mr.get("detailed_merge_status") not in ("mergeable", "not_approved"):
        reasons.append("GitLab merge checks are blocked, pending or unknown")
    if mr.get("blocking_discussions_resolved") is not True or any(
            note.get("resolvable") and not note.get("resolved")
            for thread in discussions for note in thread.get("notes", [])):
        reasons.append("Review discussions are unresolved or their status is unknown")
    pipeline = mr.get("head_pipeline") or {}
    if pipeline.get("status") != "success" or pipeline.get("sha") != head:
        reasons.append("No successful head pipeline for the exact reviewed commit")
    if not jobs:
        reasons.append("Pipeline job evidence is unavailable")
    elif any(job.get("status") != "success" and job.get("allow_failure") is not True for job in jobs):
        reasons.append("A required pipeline job did not succeed")
    return reasons


def approved_by(host, endpoint, user_id):
    state = api(host, endpoint + "/approvals")
    if not isinstance(state.get("approved_by"), list):
        raise ValueError("GitLab approval state is unavailable")
    return any(item.get("user", {}).get("id") == user_id for item in state["approved_by"])


def apply(host, endpoint, refs, review):
    user_id = api(host, "user")["id"]
    already_approved = approved_by(host, endpoint, user_id)
    current = api(host, endpoint)
    if current.get("state") != "opened" or current.get("diff_refs") != refs:
        raise ValueError("MR changed before approval; no approval action performed")
    discussions = pages(host, endpoint + "/discussions")
    jobs = pipeline_jobs(host, current)
    reasons = blockers(review, current, discussions, jobs, refs["head_sha"])
    # Recheck after collecting evidence, including pipeline replacement/reruns.
    latest = api(host, endpoint)
    if latest.get("diff_refs") != refs or latest.get("state") != "opened":
        raise ValueError("MR changed before approval; no approval action performed")
    if latest.get("head_pipeline") != current.get("head_pipeline"):
        reasons.append("Pipeline changed while approval checks were collected; rerun review")
    reasons += [reason for reason in blockers(review, latest, discussions, jobs, refs["head_sha"])
                if reason not in reasons]
    if not reasons:
        # GitLab returns 409 if a push races with this request.
        api(host, endpoint + "/approve", {"sha": refs["head_sha"]})
        if not approved_by(host, endpoint, user_id):
            raise ValueError("GitLab did not confirm this account's approval")
        return "approved", []
    if already_approved:
        # This removes only the authenticated user's approval, never all approvals.
        api(host, endpoint + "/unapprove", {})
        if approved_by(host, endpoint, user_id):
            raise ValueError("GitLab did not confirm removal of this account's approval")
        return "unapproved", reasons
    return "withheld", reasons
