import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from shared.config import GitLabSettings


class GitLabSettingsTests(unittest.TestCase):
    def settings(self, project, **extra):
        env = {"GITLAB_TOKEN": "test-token", "GITLAB_HOST": "gitlab.example.com",
               "PROJECT_URL": project, **extra}
        with patch.dict(os.environ, env, clear=True):
            settings = GitLabSettings.from_env()
            self.assertEqual(os.environ["GITLAB_HOST"], settings.host)
            self.assertEqual(os.environ["GITLAB_API_PROTOCOL"], "https")
            return settings

    def test_project_formats_use_configured_host(self):
        for project in (
            "https://gitlab.example.com/group/sub/project.git",
            "https://other.example.com/group/sub/project",
            "http://other.example.com/group/sub/project.git/",
            "ssh://git@other.example.com:2222/group/sub/project.git",
            "git@other.example.com:group/sub/project.git",
            "other.example.com:group/sub/project.git",
            "group/sub/project",
        ):
            with self.subTest(project=project):
                settings = self.settings(project)
                self.assertEqual(settings.project_path, "group/sub/project")
                self.assertEqual(settings.project_id, "group%2Fsub%2Fproject")
                self.assertEqual(settings.clone_url,
                                 "https://gitlab.example.com/group/sub/project.git")

    def test_instance_takes_precedence(self):
        settings = self.settings("group/project", GITLAB_INSTANCE_URL="https://instance.example.com:8443/")
        self.assertEqual(settings.clone_url, "https://instance.example.com:8443/group/project.git")

    def test_invalid_projects(self):
        for project in ("", "project", "https://example.com", "group/../project",
                        "group//project", "https://example.com/group/project?x=1",
                        "https://example.com/group/project#fragment", "group/.git"):
            with self.subTest(project=project), self.assertRaises(ValueError):
                self.settings(project)

    def test_invalid_instance(self):
        for instance in ("http://example.com", "https://", "https://user:pass@example.com",
                         "https://example.com/group"):
            with self.subTest(instance=instance), self.assertRaises(ValueError):
                self.settings("group/project", GITLAB_INSTANCE_URL=instance)


if __name__ == "__main__":
    unittest.main()
