#!/usr/bin/env python3
"""
run_pipeline.py

The single entry point cron should call. Runs, in order:
  1. check_and_fetch.py  - is there a new FDLE dataset? download if so.
  2. extract.py           - parse it into data.json
  3. render_index.py      - rebuild index.html
  4. render_agency.py     - rebuild agencies/*.html
  5. publish.py           - commit + push, only if something changed

If step 1 finds nothing new, the pipeline stops there and exits cleanly -
steps 2-5 don't run, so there's no risk of a no-op commit.

If any step from 2 onward fails, the pipeline reverts the working tree
(git checkout -- .) so a bad partial regeneration never gets committed,
and the repo is left exactly as it was before this run - safe to retry
next time cron fires.

USAGE
    python run_pipeline.py --repo-dir /path/to/Florida-FIBRS-Crime-Data

Expected layout inside --repo-dir:
    index.html
    readme.html
    agencies/
    data.json
    data/                  (state.json + raw/ downloaded xlsx files)
    scripts/               (this file and the others live here)
    logs/                  (pipeline.log written here)

Suggested crontab entry (daily at 6am, adjust paths):
    0 6 * * * /usr/bin/python3 /home/YOU/Florida-FIBRS-Crime-Data/scripts/run_pipeline.py --repo-dir /home/YOU/Florida-FIBRS-Crime-Data >> /home/YOU/Florida-FIBRS-Crime-Data/logs/cron.log 2>&1
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()


def log(logfile, message):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line)
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(cmd, logfile, label):
    log(logfile, f"START {label}: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        log(logfile, f"  stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        log(logfile, f"  stderr: {result.stderr.strip()}")
    log(logfile, f"DONE {label} (exit code {result.returncode})")
    return result


def revert_working_tree(repo_dir, logfile):
    log(logfile, "Reverting working tree to last committed state (git checkout -- .)")
    subprocess.run(["git", "checkout", "--", "."], cwd=repo_dir, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-dir", required=True, help="Path to the local git repo")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).resolve()
    data_dir = repo_dir / "data"
    agencies_dir = repo_dir / "agencies"
    data_json = repo_dir / "data.json"
    logs_dir = repo_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    logfile = logs_dir / "pipeline.log"

    python = sys.executable

    log(logfile, "=" * 60)
    log(logfile, "Pipeline run starting")

    # ---- 1. check for new data ----
    result = run_step(
        [python, str(SCRIPT_DIR / "check_and_fetch.py"), "--data-dir", str(data_dir)],
        logfile, "check_and_fetch"
    )
    if result.returncode == 1:
        log(logfile, "No new data. Pipeline finished (nothing to do).")
        sys.exit(0)
    if result.returncode != 0:
        log(logfile, "check_and_fetch FAILED. Pipeline stopping. Nothing was changed.")
        sys.exit(1)

    xlsx_path = result.stdout.strip().splitlines()[-1]
    log(logfile, f"New dataset: {xlsx_path}")

    # ---- 2. extract ----
    result = run_step(
        [python, str(SCRIPT_DIR / "extract.py"), xlsx_path, "-o", str(data_json)],
        logfile, "extract"
    )
    if result.returncode != 0:
        log(logfile, "extract FAILED. Reverting and stopping.")
        revert_working_tree(repo_dir, logfile)
        sys.exit(1)

    # ---- 3. render index ----
    result = run_step(
        [python, str(SCRIPT_DIR / "render_index.py"), str(data_json),
         "-o", str(repo_dir / "index.html")],
        logfile, "render_index"
    )
    if result.returncode != 0:
        log(logfile, "render_index FAILED. Reverting and stopping.")
        revert_working_tree(repo_dir, logfile)
        sys.exit(1)

    # ---- 4. render agency pages ----
    result = run_step(
        [python, str(SCRIPT_DIR / "render_agency.py"), str(data_json),
         "-o", str(agencies_dir)],
        logfile, "render_agency"
    )
    if result.returncode != 0:
        log(logfile, "render_agency FAILED. Reverting and stopping.")
        revert_working_tree(repo_dir, logfile)
        sys.exit(1)

    # ---- 5. publish ----
    dataset_end = Path(xlsx_path).stem
    commit_message = f"Update FIBRS data ({dataset_end}) (automated)"
    result = run_step(
        [python, str(SCRIPT_DIR / "publish.py"), "--repo-dir", str(repo_dir),
         "--message", commit_message],
        logfile, "publish"
    )
    if result.returncode != 0:
        log(logfile, "publish FAILED. Working tree left as-is for manual inspection "
                      "(NOT reverted, since the generated files are still valid - "
                      "only the git push failed).")
        sys.exit(1)

    log(logfile, "Pipeline run completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
