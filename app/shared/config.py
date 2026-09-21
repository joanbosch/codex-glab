from dataclasses import dataclass
import os
from urllib.parse import quote, urlsplit


def env_bool(name, default=False):
    value = os.environ.get(name, str(default)).lower()
    if value not in ("true", "false"):
        raise ValueError(f"{name} must be true or false")
    return value == "true"


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
        url = urlsplit(os.environ.get("PROJECT_URL", "").rstrip("/"))
        instance = urlsplit(os.environ.get("GITLAB_INSTANCE_URL") or
                            "https://" + os.environ.get("GITLAB_HOST", "gitlab.com"))
        if (url.scheme != "https" or instance.scheme != "https" or url.netloc != instance.netloc
                or url.username or url.password or url.query or url.fragment or not url.path.strip("/")):
            raise ValueError("PROJECT_URL must be an HTTPS project URL on the configured GitLab host")
        os.environ["GITLAB_TOKEN"] = token
        os.environ["GITLAB_HOST"] = instance.netloc
        os.environ["GITLAB_API_PROTOCOL"] = "https"
        return cls(instance.netloc, url.path.strip("/").removesuffix(".git"), token)
