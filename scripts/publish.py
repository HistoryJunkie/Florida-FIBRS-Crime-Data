#!/usr/bin/env python3
"""
publish.py

Commits and pushes changes to the repo, but only if something actually
changed - so re-running the pipeline never creates empty commits.

Assumes this machine already has working git push access to the repo's
remote (SSH key or credential helper already set up and tested manually).
This script does not handle authentication itself.

USAGE
    python publish.py --repo-dir /path/to/Florida-FIBRS-Crime-Data --message "Update FIBRS data"

Exit codes:
  0 - pushed successfully, or nothing to push (both are "success")
  1 - git command failed
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-dir", required=True, help="Path to the local git repo")
    parser.add_argument("--message", default="Update FIBRS data (automated)",
                         help="Commit message")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir)
    if not (repo_dir / ".git").exists():
        print(f"ERROR: {repo_dir} does not look like a git repo (no .git folder).",
              file=sys.stderr)
        sys.exit(1)

    # Stage everything (new agency pages, updated index.html, updated data.json, etc.)
    code, out, err = run(["git", "add", "-A"], cwd=repo_dir)
    if code != 0:
        print(f"ERROR: git add failed: {err}", file=sys.stderr)
        sys.exit(1)

    # If nothing is staged, there's nothing to publish - this is a normal,
    # successful outcome (e.g. re-running the pipeline with no new data).
    code, out, err = run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir)
    if code == 0:
        print("No changes to publish.")
        sys.exit(0)

    code, out, err = run(["git", "commit", "-m", args.message], cwd=repo_dir)
    if code != 0:
        print(f"ERROR: git commit failed: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"Committed: {out.splitlines()[0] if out else '(no output)'}")

    code, out, err = run(["git", "push"], cwd=repo_dir)
    if code != 0:
        print(f"ERROR: git push failed: {err}", file=sys.stderr)
        print("The commit was made locally but NOT pushed. You'll need to "
              "push manually and investigate (check credentials/network).",
              file=sys.stderr)
        sys.exit(1)

    print("Pushed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
