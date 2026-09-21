"""GitLab transport shared by flows; each runner owns its allowed mutations."""
import json
import subprocess
from . import process


def api(host, endpoint, payload=None, *, method=None):
    args = ["glab", "api", "--hostname", host, endpoint]
    if method is not None:
        args += ["--method", method]
    elif payload is not None:
        args += ["--method", "POST"]
    if payload is not None:
        args += ["--input", "-"]
    result = process.run(args, input=json.dumps(payload) if payload is not None else None,
                         stdout=subprocess.PIPE)
    return json.loads(result.stdout) if result.stdout.strip() else None


def pages(host, endpoint):
    result = []
    page = 1
    separator = "&" if "?" in endpoint else "?"
    while True:
        chunk = api(host, f"{endpoint}{separator}per_page=100&page={page}")
        if not isinstance(chunk, list):
            raise ValueError("Expected a paginated GitLab array")
        result.extend(chunk)
        if len(chunk) < 100:
            return result
        page += 1
