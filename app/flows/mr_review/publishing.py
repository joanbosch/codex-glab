"""MR-specific validation and discussion payloads."""
import hashlib
import json
import re

EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}

def changed_lines(patches):
    anchors = {}
    for patch in patches:
        old = new = None
        for line in patch.get("diff", "").splitlines():
            hunk = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if hunk:
                old, new = map(int, hunk.groups())
            elif old is not None:
                if line.startswith("+"):
                    anchors[(patch["new_path"], "new", new)] = patch
                    new += 1
                elif line.startswith("-"):
                    anchors[(patch["old_path"], "old", old)] = patch
                    old += 1
                elif line.startswith(" "):
                    old += 1
                    new += 1
    return anchors


def marker(head, finding):
    value = json.dumps([head, finding["path"], finding["side"], finding["line"],
                        finding["body"].strip()], ensure_ascii=False)
    return "<!-- codex-glab:" + hashlib.sha256(value.encode()).hexdigest() + " -->"


def prepare_comments(review, patches, refs):
    # Validate the entire result before the first write to GitLab.
    if not isinstance(review.get("summary"), str) or not review["summary"].strip():
        raise ValueError("Missing review summary")
    if not isinstance(review.get("general_feedback"), str):
        raise ValueError("Invalid general feedback")
    if not isinstance(review.get("findings"), list):
        raise ValueError("Invalid findings")
    anchors = changed_lines(patches)
    comments = []
    seen = set()
    for finding in review["findings"]:
        key = (finding["path"], finding["side"], finding["line"])
        if type(finding["line"]) is not int or key not in anchors:
            raise ValueError(f"Finding outside changed lines: {key}")
        if finding["severity"] not in EMOJI or not finding["body"].strip():
            raise ValueError("Invalid finding body/severity")
        suggestion = finding.get("suggestion")
        if suggestion is not None and (not isinstance(suggestion, str) or finding["side"] != "new"):
            raise ValueError("Suggestions must target added lines")
        tag = marker(refs["head_sha"], finding)
        if tag in seen:
            continue
        seen.add(tag)
        patch = anchors[key]
        position = {"position_type": "text", **refs,
                    "old_path": patch["old_path"], "new_path": patch["new_path"],
                    finding["side"] + "_line": finding["line"]}
        body = f'{EMOJI[finding["severity"]]} **{finding["severity"]}** — {finding["body"].strip()}'
        if suggestion is not None:
            fence = "`" * max(3, max((len(s) + 1 for s in re.findall(r"`+", suggestion)), default=3))
            body += f"\n\n{fence}suggestion\n{suggestion}\n{fence}"
        comments.append({"body": body + "\n\n" + tag, "position": position})
    return comments

