from dataclasses import dataclass
import os
import re
from urllib.parse import quote, urlsplit


def env_bool(name, default=False):
    value = os.environ.get(name, str(default)).lower()
    if value not in ("true", "false"):
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def project_path(value):
    value = value.strip().rstrip("/")
    if "://" in value:
        url = urlsplit(value)
        if not url.netloc or url.query or url.fragment:
            raise ValueError("PROJECT_URL must identify a GitLab project")
        path = url.path
    elif re.match(r"^(?:[^/@:]+@)?[^/:]+:", value):
        # Git's SCP-style SSH syntax: git@host:group/project.git.
        path = value.split(":", 1)[1]
    else:
        path = value
    path = path.strip("/").removesuffix(".git")
    parts = path.split("/")
    if len(parts) < 2 or any(not re.fullmatch(r"[\w.-]+", part)
                             or part in (".", "..") for part in parts):
        raise ValueError("PROJECT_URL must contain a namespace/project path")
    return path


@dataclass(frozen=True)
class GitLabSettings:
    host: str
    project_path: str
    token: str

    @property
    def project_id(self):
        return quote(self.project_path, safe="")

    @property
    def clone_url(self):
        return f"https://{self.host}/{self.project_path}.git"

    @classmethod
    def from_env(cls):
        token = os.environ.get("GITLAB_TOKEN") or os.environ.get("GITLAB_AUTH_TOKEN")
        if not token:
            raise ValueError("GITLAB_TOKEN or GITLAB_AUTH_TOKEN is required")
        path = project_path(os.environ.get("PROJECT_URL", ""))
        instance = urlsplit(os.environ.get("GITLAB_INSTANCE_URL") or
                            "https://" + os.environ.get("GITLAB_HOST", "gitlab.com"))
        if (instance.scheme != "https" or not instance.hostname
                or instance.username or instance.password or instance.query or instance.fragment
                or instance.path.strip("/")):
            raise ValueError("GITLAB_INSTANCE_URL/GITLAB_HOST must identify an HTTPS GitLab host")
        os.environ["GITLAB_TOKEN"] = token
        os.environ["GITLAB_HOST"] = instance.netloc
        os.environ["GITLAB_API_PROTOCOL"] = "https"
        return cls(instance.netloc, path, token)
