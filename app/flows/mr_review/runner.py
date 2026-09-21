"""MR-review orchestration; other flows have independent runners."""
import json
import hashlib
import os
from pathlib import Path
import re
import tempfile

from shared.config import GitLabSettings, env_bool
from shared.gitlab import api, pages
from shared.repository import clone, fetch, checkout, require_commit
from shared.codex import execute
from .publishing import prepare_comments
from . import approval


def main(spec):
    dry_run = env_bool("DRY_RUN", default=False)
    settings = GitLabSettings.from_env()
    if not os.environ.get("CODEX_ACCESS_TOKEN"):
        raise ValueError("CODEX_ACCESS_TOKEN is required")
    host = settings.host
    iid = os.environ.get("MERGE_REQUEST_IID", "")
    if not iid.isdecimal() or int(iid) < 1:
        raise ValueError("MERGE_REQUEST_IID must be a positive integer")
    endpoint = f"projects/{settings.project_id}/merge_requests/{iid}"
    mr = api(host, endpoint)
    if mr.get("state") != "opened":
        raise ValueError("The merge request is not open")
    refs = {key: (mr.get("diff_refs") or {}).get(key) for key in ("base_sha", "start_sha", "head_sha")}
    if not all(isinstance(s, str) and re.fullmatch(r"[0-9a-f]{40,64}", s) for s in refs.values()):
        raise ValueError("GitLab has not prepared the MR diff refs yet; retry later")
    patches = pages(host, endpoint + "/diffs")
    if any(p.get("collapsed") or p.get("too_large") for p in patches):
        raise ValueError("GitLab returned incomplete diffs; cannot safely anchor a complete review")
    discussions = pages(host, endpoint + "/discussions")
    notes = pages(host, endpoint + "/notes")
    issues = pages(host, endpoint + "/closes_issues")
    jobs = approval.pipeline_jobs(host, mr)
    if api(host, endpoint).get("diff_refs") != refs:
        raise ValueError("MR diff changed while collecting context; retry")
    with tempfile.TemporaryDirectory(prefix="codex-glab-") as tmp:
        root = Path(tmp)
        repo = root / "repo"
        clone(settings, repo)
        fetch(settings, repo, f"refs/merge-requests/{iid}/head")
        checkout(repo, refs["head_sha"])
        require_commit(repo, refs["base_sha"])
        context = {"mr": mr, "pipeline_jobs": jobs, "issues_closed_by_mr": issues, "notes": notes,
                   "discussions": discussions, "additional_instructions": os.environ.get(
                       "ADDITIONAL_INSTRUCTIONS", os.environ.get("ADDITIONAL_COMMENTS", ""))}
        (root / "context.json").write_text(json.dumps(context, ensure_ascii=False))
        (root / "patches.json").write_text(json.dumps(patches, ensure_ascii=False))
        output = root / "review.json"
        prompt = (spec.directory / "prompt.md").read_text() + f"\nBase SHA: {refs['base_sha']}\nContext: {root / 'context.json'}\nPatches: {root / 'patches.json'}\n"
        print("Running Codex review", flush=True)
        review = execute(repo=repo, prompt=prompt, schema=spec.directory / "output.schema.json",
                         output=output, sandbox=spec.sandbox)
        comments = prepare_comments(review, patches, refs)
        approval.validate_decision(review)
        summary = ("## 📋 Review Summary\n\n" + review["summary"] +
                   "\n\n## 🔍 General Feedback\n\n" + review["general_feedback"] +
                   f"\n\nReviewed commit: `{refs['head_sha']}`")
        if dry_run:
            reasons = approval.blockers(review, mr, discussions, jobs, refs["head_sha"])
            print(json.dumps({"discussions": comments, "summary": summary,
                              "approval_recommendation": review["decision"],
                              "approval_blockers": reasons}, ensure_ascii=False, indent=2))
            print("DRY_RUN: no GitLab writes performed")
            return
        # Re-fetch to catch updates and exact duplicates from previous attempts.
        current = api(host, endpoint)
        if current.get("state") != "opened" or current.get("diff_refs") != refs:
            raise ValueError("MR changed during review; no results published")
        existing = json.dumps(pages(host, endpoint + "/discussions") + pages(host, endpoint + "/notes"))
        posted = 0
        for comment in comments:
            tag = comment["body"].split("\n\n")[-1]
            if tag not in existing:
                api(host, endpoint + "/discussions", comment)
                posted += 1
        outcome, reasons = approval.apply(host, endpoint, refs, review)
        summary += "\n\n## Approval decision\n\n" + outcome.capitalize() + ". " + review["decision_reason"]
        if reasons:
            summary += "\n\n" + "\n".join("- " + reason for reason in reasons)
        # CI-only reruns can change the decision for the same commit.
        summary_tag = "<!-- codex-glab-summary:" + hashlib.sha256(summary.encode()).hexdigest() + " -->"
        if summary_tag not in existing:
            summary += "\n\n" + summary_tag
            api(host, endpoint + "/notes", {"body": summary})
        print(f"Review complete: {posted} inline discussions published for !{iid}; approval {outcome}")
