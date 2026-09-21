import subprocess


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)
