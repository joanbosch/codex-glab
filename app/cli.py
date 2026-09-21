import argparse
import os
import subprocess
import sys
from registry import discover


def main(argv=None):
    flows = discover()
    parser = argparse.ArgumentParser(description="Custom Codex workflows for GitLab")
    parser.add_argument("flow", nargs="?", default="mr-review", choices=sorted(flows))
    parser.add_argument("--list", action="store_true", help="List installed flows without authentication")
    args = parser.parse_args(argv)
    if args.list:
        for spec in flows.values():
            print(f"{spec.name}\t{spec.sandbox}\t{spec.description}")
        return
    spec = flows[args.flow]
    missing = [key for key in spec.required_env if not os.environ.get(key)]
    if missing:
        raise ValueError("Missing variables for " + spec.name + ": " + ", ".join(missing))
    spec.load()(spec)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Workflow failed: {exc}", file=sys.stderr)
        sys.exit(1)
