#!/usr/bin/env python3
"""
check_and_fetch.py

Checks FDLE's FIBRS Offense page for the current downloadable Excel export,
and downloads it only if it's different from the last one we processed.

Exit codes (this is how run_pipeline.py decides what to do next):
  0  - a new file was found and downloaded
  1  - no new file (page still points at the same dataset we already have)
  2  - error (page structure changed, download failed, network issue, etc.)

USAGE
    pip install requests
    python check_and_fetch.py --data-dir data

State is kept in <data-dir>/state.json. Downloaded files go in
<data-dir>/raw/. Nothing outside --data-dir is touched.

NOTE: this script was written from the FDLE FIBRS page's HTML structure as
observed on 2026-09-05, not tested against a live connection to
fdle.state.fl.us (that domain isn't reachable from the environment this was
built in). Please run it manually once and confirm it behaves before
relying on it from cron - if FDLE has changed their page layout, the
regex below is the first thing to check.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("This script requires requests. Install with: pip install requests")
    sys.exit(2)

FIBRS_PAGE_URL = "https://www.fdle.state.fl.us/cjab/fibrs"
USER_AGENT = "Mozilla/5.0 (compatible; FIBRS-data-pipeline/1.0)"

# Matches an href ending in .xlsx (with an optional query string like
# ?language=en). This page currently has exactly one such link.
XLSX_HREF_PATTERN = re.compile(r'href="([^"]*\.xlsx(?:\?[^"]*)?)"', re.IGNORECASE)


def find_current_xlsx_url():
    resp = requests.get(FIBRS_PAGE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()

    matches = XLSX_HREF_PATTERN.findall(resp.text)
    if not matches:
        raise RuntimeError(
            "No .xlsx link found on the FIBRS page. FDLE may have changed "
            "the page layout - check FIBRS_PAGE_URL manually and update "
            "XLSX_HREF_PATTERN in this script."
        )
    url = matches[0]
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://www.fdle.state.fl.us" + url
    return url


def filename_from_url(url):
    # Strip query string, keep the base filename
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    return name


def load_state(state_path):
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(state_path, state):
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def download_file(url, dest_path):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    resp.raise_for_status()
    content = resp.content

    # Sanity check: an .xlsx is a zip file and must start with "PK".
    # If FDLE's site returns an HTML error page instead (e.g. broken link,
    # maintenance page), catch that here rather than silently saving garbage.
    if content[:2] != b"PK":
        raise RuntimeError(
            f"Downloaded content from {url} doesn't look like a valid .xlsx "
            "file (missing zip header). Refusing to save it. FDLE's link "
            "may be temporarily broken, or the page structure changed."
        )

    dest_path.write_bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default="data",
                         help="Folder for state.json and downloaded files (default: data)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "state.json"

    try:
        current_url = find_current_xlsx_url()
    except Exception as e:
        print(f"ERROR checking FDLE page: {e}", file=sys.stderr)
        sys.exit(2)

    filename = filename_from_url(current_url)
    state = load_state(state_path)

    if state.get("last_url") == current_url and (raw_dir / filename).exists():
        print(f"No new data. Current dataset is still {filename}.")
        sys.exit(1)

    dest_path = raw_dir / filename
    print(f"New dataset found: {filename}")
    print(f"Downloading from {current_url} ...")

    try:
        download_file(current_url, dest_path)
    except Exception as e:
        print(f"ERROR downloading file: {e}", file=sys.stderr)
        sys.exit(2)

    state["last_url"] = current_url
    state["last_filename"] = filename
    state["last_downloaded_path"] = str(dest_path.resolve())
    save_state(state_path, state)

    print(f"Downloaded to {dest_path.resolve()}")
    # Print the path as the last line so run_pipeline.py can capture it.
    print(str(dest_path.resolve()))
    sys.exit(0)


if __name__ == "__main__":
    main()
