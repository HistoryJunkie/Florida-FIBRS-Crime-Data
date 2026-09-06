#!/usr/bin/env python3
"""
extract.py

Parses an FDLE FIBRS Offense Excel export into a single clean JSON file that
everything downstream (county index, agency detail pages) reads from. This
is the only script that needs to understand FDLE's spreadsheet layout.

USAGE
    pip install pandas openpyxl
    python extract.py FIBRS_Offense_Detail_07_2026.xlsx -o data.json

DEFINITIONS
  - A month counts as "submitted" if the agency's summed offense count for
    that month is greater than 0. A month marked "--" (not yet available)
    and a month that sums to exactly 0 are both treated as NOT submitted -
    a real Group A offense total of zero across an entire jurisdiction for
    a full month is implausible enough that it's treated as a reporting
    gap, not a crime-free month.
  - "Current dataset month" is parsed from the source filename (e.g.
    "07_2026" or "07-2026" -> July 2026) and is the last month included in
    the coverage window.
  - "Total months" (Y) = number of months from January 2021 through the
    current dataset month, inclusive. This is the denominator agencies are
    judged against, e.g. "55 of 67 months submitted."
  - An agency is "current" if it has a real (nonzero) submission for the
    dataset's most recent month.
  - Offense-type breakdowns are tracked both all-time and per calendar
    year, so downstream pages can offer a year filter on top of the
    all-time view.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("This script requires pandas and openpyxl. Install with:")
    print("    pip install pandas openpyxl")
    sys.exit(1)


DATASET_START = (2021, 1)  # January 2021, per FDLE - FIBRS coverage begins here


def parse_dataset_end_from_filename(path: Path):
    """Extract (year, month) from a filename like
    'FIBRS_Offense_Detail_07_2026.xlsx' or '...07-2026.xlsx'."""
    m = re.search(r"(\d{2})[_-](\d{4})", path.stem)
    if not m:
        raise ValueError(
            f"Could not parse month/year from filename '{path.name}'. "
            "Expected a pattern like '07_2026' or '07-2026' somewhere in the name."
        )
    month, year = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12):
        raise ValueError(f"Parsed month {month} out of range from filename '{path.name}'.")
    return year, month


def months_between_inclusive(start_year, start_month, end_year, end_month):
    return (end_year - start_year) * 12 + (end_month - start_month) + 1


def month_labels(start_year, start_month, count):
    labels = []
    y, m = start_year, start_month
    for _ in range(count):
        labels.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return labels


def offense_type_columns(df):
    """Offense-type columns start at index 3 and run in 12-column blocks
    (Jan-Dec) per offense type, named in row 1 of the sheet."""
    header_row = df.iloc[1, :].tolist()
    return [(i, str(v).strip()) for i, v in enumerate(header_row)
            if pd.notna(v) and i >= 3]


def extract(xlsx_path: Path):
    end_year, end_month = parse_dataset_end_from_filename(xlsx_path)
    total_months = months_between_inclusive(*DATASET_START, end_year, end_month)
    labels = month_labels(*DATASET_START, total_months)
    label_index = {label: i for i, label in enumerate(labels)}

    xl = pd.ExcelFile(xlsx_path)

    # agency_key -> {"county": str, "monthly": [0]*total_months, "offense_types": {}}
    agencies = {}

    for sheet in xl.sheet_names:
        sheet_year_match = re.search(r"(\d{4})", sheet)
        if not sheet_year_match:
            continue
        sheet_year = int(sheet_year_match.group(1))

        df = xl.parse(sheet, header=None)
        cols = offense_type_columns(df)

        for _, row in df.iterrows():
            county = row[0]
            agency = row[1]
            if pd.isna(county) or pd.isna(agency):
                continue
            county, agency = str(county).strip(), str(agency).strip()
            if county == "County" or agency == "Agency Name":
                continue  # header row leaked into data

            rec = agencies.setdefault(agency, {
                "county": county,
                "monthly": [0] * total_months,
                "offense_types": {},
                "offense_types_by_year": {},
            })

            year_bucket = rec["offense_types_by_year"].setdefault(str(sheet_year), {})

            for m in range(12):
                label = f"{sheet_year}-{m+1:02d}"
                if label not in label_index:
                    continue  # month outside the dataset's coverage window
                idx = label_index[label]
                month_total = 0
                for start_col, offense_name in cols:
                    val = row[start_col + m]
                    if pd.isna(val) or val == "--":
                        continue
                    month_total += val
                    rec["offense_types"][offense_name] = (
                        rec["offense_types"].get(offense_name, 0) + int(val)
                    )
                    year_bucket[offense_name] = year_bucket.get(offense_name, 0) + int(val)
                rec["monthly"][idx] += int(month_total)

    # ---- derive per-agency summary fields ----
    counties = {}
    for agency, rec in agencies.items():
        monthly = rec["monthly"]
        submitted_months = sum(1 for v in monthly if v > 0)
        current = monthly[-1] > 0
        total_offenses = sum(monthly)
        offense_types = {k: v for k, v in rec["offense_types"].items() if v > 0}
        offense_types_by_year = {
            year: {k: v for k, v in types.items() if v > 0}
            for year, types in rec["offense_types_by_year"].items()
        }

        county_bucket = counties.setdefault(rec["county"], {"agencies": {}})
        county_bucket["agencies"][agency] = {
            "monthly": monthly,
            "submitted_months": submitted_months,
            "total_months": total_months,
            "current": current,
            "total_offenses": total_offenses,
            "offense_types": offense_types,
            "offense_types_by_year": offense_types_by_year,
        }

    return {
        "meta": {
            "source_file": xlsx_path.name,
            "dataset_start": f"{DATASET_START[0]}-{DATASET_START[1]:02d}",
            "dataset_end": f"{end_year}-{end_month:02d}",
            "total_months": total_months,
            "month_labels": labels,
            "generated": date.today().isoformat(),
        },
        "counties": counties,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx_path", help="Path to the FDLE FIBRS Offense Excel export")
    parser.add_argument("-o", "--output", default="data.json",
                         help="Output JSON path (default: data.json)")
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx_path)
    if not xlsx_path.exists():
        print(f"File not found: {xlsx_path}")
        sys.exit(1)

    print(f"Reading {xlsx_path} ...")
    result = extract(xlsx_path)

    out_path = Path(args.output)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    n_counties = len(result["counties"])
    n_agencies = sum(len(c["agencies"]) for c in result["counties"].values())
    print(f"Extracted {n_agencies} agencies across {n_counties} counties.")
    print(f"Dataset window: {result['meta']['dataset_start']} to "
          f"{result['meta']['dataset_end']} ({result['meta']['total_months']} months).")
    print(f"Wrote {out_path.resolve()}")


if __name__ == "__main__":
    main()
