"""Git authentication is scoped to transport, never persisted in the checkout."""
import base64
import os
from . import process


def transport_env(settings):
    auth = base64.b64encode(("oauth2:" + settings.token).encode()).decode()
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "http.extraHeader", "GIT_CONFIG_VALUE_0": "Authorization: Basic " + auth,
            "GIT_CONFIG_KEY_1": "http.followRedirects", "GIT_CONFIG_VALUE_1": "false"}


def clone(settings, destination):
    process.run(["git", "clone", "--no-checkout", settings.clone_url, str(destination)],
                env=transport_env(settings))


def fetch(settings, repo, ref):
    process.run(["git", "-C", str(repo), "fetch", "origin", ref], env=transport_env(settings))


def checkout(repo, sha):
    process.run(["git", "-C", str(repo), "checkout", "--detach", sha])


def require_commit(repo, sha):
    process.run(["git", "-C", str(repo), "cat-file", "-e", sha + "^{commit}"])
