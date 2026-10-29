#!/usr/bin/env python3
"""Fetch Scholar on this computer and push only citation data from a temporary clone."""

import argparse
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = ["data/scholar-citations.json", "data/scholar-citations.js"]


def run(arguments, cwd, env, capture=False):
    return subprocess.run(arguments, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def publish(repo_path):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    ssh = "/usr/bin/ssh -o UseKeychain=yes" if sys.platform == "darwin" else "ssh"
    env.setdefault("GIT_SSH_COMMAND", ssh + " -o BatchMode=yes -o ConnectTimeout=20")
    if sys.platform == "darwin" and not ssl.get_default_verify_paths().cafile:
        env.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
    remote = run(["git", "remote", "get-url", "origin"], repo_path, env, True).strip()
    # Preserve the user's identity, including any repository-specific setting.
    identity = {key: run(["git", "config", "--get", key], repo_path, env, True).strip()
                for key in ("user.name", "user.email")}
    with tempfile.TemporaryDirectory(prefix="scholar-sync-") as directory:
        checkout = Path(directory) / "repository"
        run(["git", "clone", "--depth=1", "--filter=blob:none", "--no-checkout",
             "--branch", "main", remote, str(checkout)], repo_path, env)
        subprocess.run(["git", "sparse-checkout", "set", "--no-cone", "--stdin"],
                       cwd=checkout, env=env, check=True, text=True,
                       input="/scripts/\n/data/scholar-citations.json\n/data/scholar-citations.js\n")
        run(["git", "checkout", "main"], checkout, env)
        before = json.loads((checkout / DATA_FILES[0]).read_text(encoding="utf-8"))
        run([sys.executable, "scripts/sync_citations.py"], checkout, env)
        after = json.loads((checkout / DATA_FILES[0]).read_text(encoding="utf-8"))
        changed_counts = sum(paper.get("citations") != before.get("publications", {}).get(key, {}).get("citations")
                             for key, paper in after["publications"].items())
        run(["git", "add", "--", *DATA_FILES], checkout, env)
        staged = set(run(["git", "diff", "--cached", "--name-only"], checkout, env, True).splitlines())
        if not staged:
            print("Citation data is unchanged; nothing to publish.")
            return
        if not staged.issubset(DATA_FILES):
            raise RuntimeError("Unexpected staged files; refusing to publish.")
        for key, value in identity.items():
            run(["git", "config", key, value], checkout, env)
        run(["git", "commit", "-m", "Update Google Scholar citation counts"], checkout, env)
        # A concurrent main update is rejected safely. Never force-push or alter
        # the original checkout; the next run starts from the newest remote main.
        run(["git", "push", "origin", "HEAD:main"], checkout, env)
        revision = run(["git", "rev-parse", "HEAD"], checkout, env, True).strip()
        print("Published citation snapshot: " + revision)
        print("Citation counts changed: " + str(changed_counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", type=Path, default=ROOT)
    args = parser.parse_args()
    publish(args.repo_path.resolve())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Local citation sync failed: " + str(error), file=sys.stderr)
        sys.exit(1)
