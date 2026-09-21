import json
import os
from . import process


def environment():
    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CODEX_ACCESS_TOKEN"}
    return {key: value for key, value in os.environ.items() if key in allowed}


def execute(*, repo, prompt, schema, output, sandbox="read-only"):
    if sandbox not in ("read-only", "workspace-write"):
        raise ValueError("Flows must explicitly use read-only or workspace-write")
    args = ["codex", "exec", "--sandbox", sandbox, "--ephemeral", "--color", "never",
            "--output-schema", str(schema), "--output-last-message", str(output), "-"]
    if os.environ.get("CODEX_MODEL"):
        args[2:2] = ["--model", os.environ["CODEX_MODEL"]]
    process.run(args, cwd=repo, env=environment(), input=prompt)
    return json.loads(output.read_text())
