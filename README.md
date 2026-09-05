# Florida FIBRS Crime Data

A GitHub-contribution-style heatmap of monthly crime offense submissions for every law enforcement agency in Florida, built from the state's official FIBRS data.

**Live site:** https://historyjunkie.github.io/Florida-FIBRS-Crime-Data/

For an explanation of what the data shows, where it comes from, and how the numbers are calculated, see the "About This Data" page linked from the site itself (readme.html) - that page is regenerated automatically and always reflects the current dataset. This file, by contrast, only describes the project and how to run it, and won't go stale as new data comes in.

## What this is

Florida's Department of Law Enforcement (FDLE) publishes FIBRS (Florida Incident-Based Reporting System) data monthly - the number of offenses each law enforcement agency in the state reported, broken down by offense category. This project turns that raw spreadsheet into a browsable static website:

- A homepage listing every Florida county and every reporting agency within it, with a Current/Not Current flag and a months-submitted count
- A detail page per agency with a monthly heatmap (2021-present), a trend chart, and an offense-type breakdown

The whole site is static HTML/CSS/JS - no server, no database, no build step beyond the Python scripts described below.

## How it works

1. **check_and_fetch.py** checks FDLE's FIBRS page for a new Excel export. If it's the same file as last time, it stops here and does nothing else.
2. **extract.py** parses the Excel file into a single clean `data.json`, computing which months each agency actually submitted (a month is only counted as submitted if its offense total is greater than zero - a real Group A offense count of zero for an entire jurisdiction is implausible enough to treat as a reporting gap, not a crime-free month).
3. **render_index.py** builds `index.html` from `data.json`.
4. **render_agency.py** builds every page in `agencies/` from `data.json`.
5. **publish.py** commits and pushes to GitHub, but only if something actually changed.

**run_pipeline.py** runs all five steps in order and is the one script cron actually calls. If any step from extraction onward fails, it reverts the working tree (`git checkout -- .`) so a bad partial run never gets committed.

## Repo layout

```
index.html          the homepage (generated - don't hand-edit)
readme.html          "about this data" page (generated - don't hand-edit)
agencies/*.html      one page per agency (generated - don't hand-edit)
data.json            the extracted dataset (generated - don't hand-edit)
data/
  state.json         tracks the last-seen FDLE file, so re-runs skip unchanged data
  raw/               downloaded .xlsx snapshots from FDLE
scripts/
  extract.py
  render_index.py
  render_agency.py
  check_and_fetch.py
  publish.py
  run_pipeline.py
logs/
  pipeline.log       written by run_pipeline.py on every run
venv/                local Python virtual environment (not tracked in git)
```

Anything generated (index.html, readme.html, agencies/, data.json) is meant to be overwritten by the pipeline every run. Don't hand-edit those files directly - changes will just get replaced the next time the pipeline runs. If the site's look needs to change, edit the templates inside the render scripts instead.

## Running it manually

```
cd ~/fibrs-data-repo
source venv/bin/activate
python3 scripts/run_pipeline.py --repo-dir ~/fibrs-data-repo
```

Or run each step individually if you want to inspect the output before it publishes:

```
python3 scripts/check_and_fetch.py --data-dir data
python3 scripts/extract.py data/raw/<the-downloaded-file>.xlsx -o data.json
python3 scripts/render_index.py data.json -o index.html
python3 scripts/render_agency.py data.json -o agencies
python3 scripts/publish.py --repo-dir ~/fibrs-data-repo --message "Update FIBRS data"
```

## Automated runs (cron)

Use absolute paths in the crontab entry, since cron doesn't run with your normal shell environment. Replace the paths below with wherever this repo actually lives on your machine:

```
0 6 * * * /path/to/fibrs-data-repo/venv/bin/python3 /path/to/fibrs-data-repo/scripts/run_pipeline.py --repo-dir /path/to/fibrs-data-repo >> /path/to/fibrs-data-repo/logs/cron.log 2>&1
```

This checks daily. Since check_and_fetch.py exits immediately when there's nothing new, daily checks are cheap even though FDLE only republishes roughly monthly.

## First-time setup on a new machine

```
git clone git@github.com:HistoryJunkie/Florida-FIBRS-Crime-Data.git
cd Florida-FIBRS-Crime-Data
python3 -m venv venv
source venv/bin/activate
pip install pandas openpyxl requests
```

Git push needs to work without any interactive prompt for cron to function - an SSH key added to your GitHub account (with no passphrase, or with an agent that persists across reboots) is the simplest way to get there. Test with `git push` manually before adding anything to crontab.

## Data source

FDLE Criminal Justice Analytics Bureau, FIBRS Offense dashboard:
https://www.fdle.state.fl.us/cjab/fibrs

## Known issues with the underlying data

This isn't a clean, mature dataset, and the numbers should be read with that in mind:

- **FIBRS itself is a relatively new, still-rolling-out system.** Florida transitioned from decades of summary-based crime reporting to this incident-based system starting in 2021, driven by an FBI mandate. Reporting is legally required under Florida Administrative Code Rule 11C-4.010, but standing up FIBRS requires each individual agency to update its own records-management system and establish a system-to-system data feed to FDLE - a technical and administrative lift that has clearly happened at very different speeds across the state's agencies.
- **A large share of agencies are still not consistently reporting.** Many show partial history, long gaps, or stopped submitting entirely partway through the dataset. This looks like an ongoing integration and onboarding problem across Florida law enforcement generally, not an issue specific to any one agency.
- **Treat unusually low or zero-offense months with suspicion, not as good news.** A real drop to zero Group A offenses for an entire jurisdiction in a given month is implausible for any agency serving an actual population. When you see a very low or empty month (or a striped/blank cell on an agency's page), the far more likely explanation is a reporting or integration failure on that agency's end for that period - not that crime actually stopped. This site's own logic reflects that assumption: a month with a total offense count of zero is treated the same as a month with no submission at all, specifically because a genuine zero is judged implausible.
- **A sudden large jump in an agency's numbers may mean their reporting got fixed, not that crime got worse.** The reverse of the point above: if an agency goes from near-zero to a normal-looking volume, that's more consistent with their FIBRS integration starting to work correctly than with an actual crime spike.

None of this means the data is useless - it's the same data FDLE and the FBI both use - but the gaps and low points are informative about reporting infrastructure first, and about actual crime trends only once you've accounted for that.

