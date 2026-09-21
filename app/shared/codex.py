import json
import os
import subprocess
import sys
from . import process


def environment():
    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CODEX_ACCESS_TOKEN"}
    return {key: value for key, value in os.environ.items() if key in allowed}


def check_linux_sandbox(repo):
    """Detect blocked user namespaces before spending tokens on a review."""
    if sys.platform != "linux":
        return
    try:
        process.run(["bwrap", "--unshare-user", "--unshare-pid", "--unshare-net",
                     "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev",
                     "--", "/bin/true"], cwd=repo, env=environment(),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ValueError(
            "Linux sandbox preflight failed before calling Codex. Install bubblewrap "
            "and configure the worker's kernel and container seccomp/AppArmor policy "
            "to permit unprivileged user namespaces. Rebuilding the image alone cannot "
            "change host permissions. Details: " + (detail or "unknown error").strip()
        ) from exc


def execute(*, repo, prompt, schema, output, sandbox="read-only"):
    if sandbox not in ("read-only", "workspace-write", "danger-full-access"):
        raise ValueError("Unsupported flow sandbox")
    if sandbox != "danger-full-access":
        check_linux_sandbox(repo)
    args = ["codex", "exec", "--sandbox", sandbox, "--ephemeral", "--color", "never",
            "--output-schema", str(schema), "--output-last-message", str(output), "-"]
    if sandbox == "danger-full-access":
        args[2:2] = ["--config", 'approval_policy="never"']
    if os.environ.get("CODEX_MODEL"):
        args[2:2] = ["--model", os.environ["CODEX_MODEL"]]
    effort = os.environ.get("CODEX_REASONING_EFFORT")
    if effort:
        if effort not in ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"):
            raise ValueError("Invalid CODEX_REASONING_EFFORT")
        args[2:2] = ["--config", "model_reasoning_effort=" + json.dumps(effort)]
    process.run(args, cwd=repo, env=environment(), input=prompt)
    return json.loads(output.read_text())
