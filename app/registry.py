"""Discover only flows packaged into this image, never from a cloned repository."""
from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import re

FLOW_ROOT = Path(__file__).resolve().parent / "flows"


@dataclass(frozen=True)
class FlowSpec:
    name: str
    description: str
    sandbox: str
    required_env: tuple
    directory: Path

    def load(self):
        return importlib.import_module(f"flows.{self.directory.name}.runner").main


def discover(root=FLOW_ROOT):
    result = {}
    for manifest in sorted(root.glob("*/flow.json")):
        data = json.loads(manifest.read_text())
        if not re.fullmatch(r"[a-z][a-z0-9_]*", manifest.parent.name):
            raise ValueError(f"Invalid flow directory: {manifest.parent.name}")
        name = data["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name in result:
            raise ValueError(f"Invalid or duplicate flow name: {name}")
        if data["sandbox"] not in ("read-only", "workspace-write", "danger-full-access"):
            raise ValueError(f"Unsupported sandbox for {name}")
        if not isinstance(data["required_env"], list) or not all(
                isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in data["required_env"]):
            raise ValueError(f"Invalid required_env for {name}")
        for file in ("runner.py", "prompt.md", "output.schema.json"):
            if not (manifest.parent / file).is_file():
                raise ValueError(f"Missing {file} for {name}")
        result[name] = FlowSpec(name, data["description"], data["sandbox"],
                                tuple(data["required_env"]), manifest.parent)
    return result
