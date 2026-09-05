#!/usr/bin/env python3
"""
render_agency.py

Builds one HTML detail page per agency in data.json: monthly heatmap
(2021-2026), stat cards, a trend line chart, and an offense-type
breakdown. Pages are written to <output-dir>/<slug>.html, meant to sit in
an "agencies" subfolder next to index.html and readme.html.

USAGE
    python render_agency.py data.json -o agencies

Reads only data.json (produced by extract.py). Does not touch the source
Excel file, index.html, or readme.html.

Definitions match render_index.py: a month counts as submitted if its
offense total is greater than 0. Months beyond the dataset's current
coverage window (e.g. Aug-Dec of the latest year, before FDLE has
published them) are shown as "not yet published" rather than "not
submitted" - a small distinction worth preserving since one is a real gap
and the other just hasn't happened in the data yet.
"""

import argparse
import json
import re
import sys
from pathlib import Path

MONTH_NAMES_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def slugify(name):
    s = name.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def build_full_grid(month_labels, values, dataset_end):
    """Pads the dataset's month list out to full calendar years, so every
    agency's heatmap always spans complete years from 2021 through the
    year of dataset_end. Months after dataset_end get value None (beyond
    the dataset's coverage window, distinct from a real reporting gap)."""
    start_year = int(month_labels[0].split("-")[0])
    end_year = int(dataset_end.split("-")[0])

    label_to_value = dict(zip(month_labels, values))
    grid = {}  # year -> [12 values], None = beyond dataset coverage
    for year in range(start_year, end_year + 1):
        row = []
        for m in range(1, 13):
            label = f"{year}-{m:02d}"
            row.append(label_to_value.get(label))  # None if not in dataset window
        grid[str(year)] = row
    return grid


def compute_stats(month_labels, values):
    submitted = [(label, v) for label, v in zip(month_labels, values) if v and v > 0]
    if not submitted:
        return None
    total = sum(v for _, v in submitted)
    avg = round(total / len(submitted))
    highest = max(submitted, key=lambda x: x[1])
    lowest = min(submitted, key=lambda x: x[1])
    return {
        "total": total,
        "avg": avg,
        "highest": {"label": highest[0], "value": highest[1]},
        "lowest": {"label": lowest[0], "value": lowest[1]},
    }


def label_to_display(label):
    year, month = label.split("-")
    return f"{MONTH_NAMES_SHORT[int(month)-1]} {year}"


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<style>
  :root{
    --bg:#0d1117;
    --panel:#161b22;
    --border:#30363d;
    --text:#c9d1d9;
    --muted:#8b949e;
    --l1:#0e4429;
    --l2:#006d32;
    --l3:#26a641;
    --l4:#39d353;
    --na-stripe:#21262d;
    --accent:#58a6ff;
    --good:#39d353;
    --bad:#f85149;
  }
  *{box-sizing:border-box;}
  body{
    margin:0;
    background:var(--bg);
    color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    padding:clamp(20px,4vw,40px) clamp(16px,4vw,24px);
  }
  .wrap{max-width:900px;margin:0 auto;}
  .nav{
    display:flex;justify-content:space-between;align-items:center;
    margin-bottom:24px;padding-bottom:14px;border-bottom:1px solid var(--border);
    flex-wrap:wrap;gap:10px;
  }
  .nav .site-name{font-size:13px;font-weight:600;color:var(--muted);}
  .nav .links{display:flex;gap:8px;flex-wrap:wrap;}
  .nav a{
    color:var(--accent);text-decoration:none;font-size:13px;font-weight:600;
    border:1px solid var(--border);padding:6px 12px;border-radius:6px;white-space:nowrap;
  }
  .nav a:hover{background:rgba(88,166,255,0.1);}
  .header{margin-bottom:22px;}
  .breadcrumb{font-size:12px;color:var(--muted);margin:0 0 6px;}
  h1{font-size:clamp(20px,4.5vw,28px);font-weight:700;margin:0 0 6px;}
  .subtitle{color:var(--muted);font-size:13px;margin:0;display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
  .status-pill{
    display:inline-flex;align-items:center;gap:5px;
    font-size:11.5px;font-weight:600;
    padding:2px 9px;border-radius:999px;
    border:1px solid var(--border);
  }
  .status-pill .dot{width:7px;height:7px;border-radius:50%;}
  .status-pill.current{color:var(--good);}
  .status-pill.current .dot{background:var(--good);}
  .status-pill.stale{color:var(--bad);}
  .status-pill.stale .dot{background:var(--bad);}
  .no-data-banner{
    background:var(--panel);border:1px solid var(--border);border-radius:6px;
    padding:20px;font-size:13px;color:var(--muted);margin-bottom:22px;
  }
  .stat-row{
    display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
    gap:12px;margin:24px 0;
  }
  .stat-card{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:14px 16px;}
  .stat-card .label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:6px;}
  .stat-card .value{font-size:clamp(18px,3.5vw,22px);font-weight:700;color:#fff;}
  .stat-card .detail{font-size:11px;color:var(--muted);margin-top:4px;}
  .section{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:clamp(16px,3.5vw,24px);margin-bottom:22px;}
  .section h2{font-size:14px;font-weight:700;color:var(--accent);margin:0 0 16px;}
  .graph{display:flex;gap:clamp(4px,1.5vw,10px);}
  .year-labels{display:flex;flex-direction:column;gap:clamp(2px,0.8vw,3px);padding-top:18px;flex-shrink:0;}
  .year-labels div{height:clamp(20px,5.5vw,28px);line-height:clamp(20px,5.5vw,28px);font-size:clamp(10px,2.6vw,12px);color:var(--muted);text-align:right;}
  .grid-wrap{flex:1;min-width:0;}
  .month-row{display:grid;grid-template-columns:repeat(12,1fr);font-size:clamp(9px,2.2vw,11px);color:var(--muted);margin-bottom:4px;}
  .month-row div{text-align:center;}
  .row{display:grid;grid-template-columns:repeat(12,1fr);gap:clamp(1.5px,0.6vw,3px);margin-bottom:clamp(1.5px,0.6vw,3px);}
  .cell{
    height:clamp(20px,5.5vw,28px);border-radius:3px;border:1px solid rgba(255,255,255,0.04);
    position:relative;display:flex;align-items:center;justify-content:center;
    font-size:clamp(8px,2vw,11px);font-variant-numeric:tabular-nums;color:rgba(255,255,255,0.85);
  }
  .cell.l1{background:var(--l1);}
  .cell.l2{background:var(--l2);}
  .cell.l3{background:var(--l3);}
  .cell.l4{background:var(--l4);}
  .cell.na{background:repeating-linear-gradient(45deg,var(--na-stripe),var(--na-stripe) 3px,#1b1f26 3px,#1b1f26 6px);color:var(--muted);}
  .cell:hover::after{
    content:attr(data-tip);position:absolute;bottom:130%;left:50%;transform:translateX(-50%);
    background:#1c2128;border:1px solid var(--border);color:var(--text);padding:5px 8px;
    font-size:11px;white-space:nowrap;border-radius:4px;z-index:10;box-shadow:0 4px 10px rgba(0,0,0,0.4);
  }
  .footer{display:flex;justify-content:space-between;align-items:center;margin-top:16px;font-size:11px;color:var(--muted);flex-wrap:wrap;gap:6px;}
  .legend{display:flex;align-items:center;gap:4px;}
  .legend .cell{height:11px;width:11px;border-radius:2px;}
  .trend-svg{width:100%;height:auto;display:block;}
  .trend-caption{font-size:11px;color:var(--muted);margin-top:10px;}
  .offense-bar-row{display:flex;align-items:center;gap:10px;margin-bottom:9px;}
  .offense-bar-row .name{width:clamp(110px,26vw,190px);flex-shrink:0;font-size:12.5px;color:var(--text);text-align:right;}
  .offense-bar-row .bar-track{flex:1;background:#0d1117;border:1px solid var(--border);border-radius:4px;height:18px;position:relative;overflow:hidden;}
  .offense-bar-row .bar-fill{height:100%;background:linear-gradient(90deg,var(--l2),var(--l4));border-radius:3px 0 0 3px;}
  .offense-bar-row .count{width:88px;flex-shrink:0;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;}
  .offense-bar-row .count strong{color:#fff;}
  details.offense-more{margin-top:14px;}
  details.offense-more summary{cursor:pointer;font-size:12.5px;color:var(--accent);font-weight:600;list-style:none;}
  details.offense-more summary::-webkit-details-marker{display:none;}
  details.offense-more summary:hover{text-decoration:underline;}
  .offense-table{width:100%;border-collapse:collapse;margin-top:14px;font-size:12.5px;}
  .offense-table th{text-align:left;color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.03em;padding:6px 8px;border-bottom:1px solid var(--border);}
  .offense-table td{padding:7px 8px;border-bottom:1px solid #21262d;}
  .offense-table td.num{text-align:right;font-variant-numeric:tabular-nums;color:var(--text);}
  .offense-table tr:hover td{background:rgba(255,255,255,0.02);}
</style>
</head>
<body>
<div class="wrap">

  <div class="nav">
    <span class="site-name">Florida FIBRS Crime Data</span>
    <div class="links">
      <a href="../index.html#county-__COUNTY_SLUG__">__COUNTY__ County</a>
      <a href="../index.html">All Agencies</a>
      <a href="../readme.html">About This Data</a>
    </div>
  </div>

  <div class="header">
    <p class="breadcrumb">__COUNTY__ County -&gt; __AGENCY_NAME__</p>
    <h1>__AGENCY_NAME__</h1>
    <p class="subtitle">
      FIBRS monthly offense submissions, __DATASET_START_DISPLAY__ - __DATASET_END_DISPLAY__
      <span class="status-pill __STATUS_CLASS__"><span class="dot"></span>__STATUS_LABEL__</span>
    </p>
  </div>

__BODY__

</div>
</body>
</html>
"""

BODY_NO_DATA = """  <div class="no-data-banner">
    This agency has no FIBRS offense data in the source export for any month, __DATASET_START_DISPLAY__ through __DATASET_END_DISPLAY__.
  </div>"""

BODY_WITH_DATA = """  <div class="stat-row">
    <div class="stat-card">
      <div class="label">Total Offenses</div>
      <div class="value">__TOTAL__</div>
      <div class="detail">Across __SUBMITTED_MONTHS__ reported months</div>
    </div>
    <div class="stat-card">
      <div class="label">Avg per Month</div>
      <div class="value">__AVG__</div>
      <div class="detail">Reported months only</div>
    </div>
    <div class="stat-card">
      <div class="label">Highest Month</div>
      <div class="value">__HIGHEST_VALUE__</div>
      <div class="detail">__HIGHEST_LABEL__</div>
    </div>
    <div class="stat-card">
      <div class="label">Lowest Month</div>
      <div class="value">__LOWEST_VALUE__</div>
      <div class="detail">__LOWEST_LABEL__</div>
    </div>
    <div class="stat-card">
      <div class="label">Months Submitted</div>
      <div class="value">__SUBMITTED_MONTHS__ of __TOTAL_MONTHS__</div>
      <div class="detail">Since January 2021</div>
    </div>
  </div>

  <div class="section">
    <h2>Monthly Submissions</h2>
    <div class="graph">
      <div class="year-labels" id="yearLabels"></div>
      <div class="grid-wrap">
        <div class="month-row" id="monthRow"></div>
        <div id="rows"></div>
      </div>
    </div>
    <div class="footer">
      <div>Striped = not submitted, or not yet published for recent months</div>
      <div class="legend">
        Less
        <div class="cell l1"></div>
        <div class="cell l2"></div>
        <div class="cell l3"></div>
        <div class="cell l4"></div>
        More
      </div>
    </div>
  </div>

  <div class="section">
    <h2>Trend Over Time</h2>
    <div id="trendChart"></div>
    <p class="trend-caption">Total offenses reported per month, chronologically. Gaps indicate not submitted or not yet published.</p>
  </div>

__OFFENSE_SECTION__

<script>
const grid = __GRID_JS__;
const years = Object.keys(grid);

function levelFor(v, min, max){
  if(v === null || v === undefined || v === 0) return 'na';
  const range = max - min || 1;
  const pct = (v - min) / range;
  if(pct < 0.25) return 'l1';
  if(pct < 0.5) return 'l2';
  if(pct < 0.75) return 'l3';
  return 'l4';
}

const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const flatValues = [];
years.forEach(y => grid[y].forEach(v => flatValues.push(v)));
const submittedValues = flatValues.filter(v => v !== null && v > 0);
const max = Math.max(...submittedValues);
const min = Math.min(...submittedValues);
const datasetEndYear = __DATASET_END_YEAR__;
const datasetEndMonth = __DATASET_END_MONTH__;

const monthRow = document.getElementById('monthRow');
months.forEach(m => {
  const d = document.createElement('div');
  d.textContent = m;
  monthRow.appendChild(d);
});

const yearLabels = document.getElementById('yearLabels');
const rows = document.getElementById('rows');

years.forEach(year => {
  const yl = document.createElement('div');
  yl.textContent = year;
  yearLabels.appendChild(yl);

  const row = document.createElement('div');
  row.className = 'row';
  grid[year].forEach((v, i) => {
    const cell = document.createElement('div');
    cell.className = 'cell ' + levelFor(v, min, max);
    cell.textContent = (v === null || v === 0) ? '-' : v;
    const beyondDataset = (parseInt(year) > datasetEndYear) ||
      (parseInt(year) === datasetEndYear && (i + 1) > datasetEndMonth);
    let tip;
    if(beyondDataset){
      tip = `${months[i]} ${year}: not yet published`;
    } else if(v === null || v === 0){
      tip = `${months[i]} ${year}: not submitted`;
    } else {
      tip = `${months[i]} ${year}: ${v} offense${v === 1 ? '' : 's'} reported`;
    }
    cell.setAttribute('data-tip', tip);
    row.appendChild(cell);
  });
  rows.appendChild(row);
});

const chartW = 800, chartH = 220;
const padL = 36, padR = 12, padT = 12, padB = 24;
const plotW = chartW - padL - padR;
const plotH = chartH - padT - padB;
const n = flatValues.length;

function xFor(i){ return padL + (i / (n - 1)) * plotW; }
function yFor(v){ return padT + plotH - ((v - 0) / (max - 0)) * plotH; }

let pathParts = [];
let segmentOpen = false;
let points = [];
let flatIdx = 0;
years.forEach(year => {
  grid[year].forEach((v, i) => {
    const x = xFor(flatIdx);
    if(v === null || v === 0){
      segmentOpen = false;
    } else {
      const y = yFor(v);
      points.push({x, y, label: `${months[i]} ${year}`, value: v});
      if(!segmentOpen){
        pathParts.push(`M ${x.toFixed(1)} ${y.toFixed(1)}`);
        segmentOpen = true;
      } else {
        pathParts.push(`L ${x.toFixed(1)} ${y.toFixed(1)}`);
      }
    }
    flatIdx++;
  });
});
const pathD = pathParts.join(' ');

const yTicks = [0, Math.round(max/2), max];
const yTickEls = yTicks.map(t => {
  const y = yFor(t);
  return `<line x1="${padL}" y1="${y}" x2="${chartW-padR}" y2="${y}" stroke="#30363d" stroke-width="1" stroke-dasharray="2,3"/>
          <text x="${padL-8}" y="${y+4}" fill="#8b949e" font-size="10" text-anchor="end">${t}</text>`;
}).join('');

const yearTickEls = years.map((y, idx) => {
  const x = xFor(idx * 12);
  return `<text x="${x}" y="${chartH-6}" fill="#8b949e" font-size="10" text-anchor="start">${y}</text>`;
}).join('');

const dotEls = points.map(p =>
  `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="2.5" fill="#39d353"><title>${p.label}: ${p.value} offenses</title></circle>`
).join('');

document.getElementById('trendChart').innerHTML = `
  <svg class="trend-svg" viewBox="0 0 ${chartW} ${chartH}" xmlns="http://www.w3.org/2000/svg">
    ${yTickEls}
    ${yearTickEls}
    <path d="${pathD}" fill="none" stroke="#39d353" stroke-width="2"/>
    ${dotEls}
  </svg>`;

const offenseTotals = __OFFENSE_JS__;
const offenseEntries = Object.entries(offenseTotals).sort((a,b) => b[1]-a[1]);
if(offenseEntries.length > 0){
  const offenseGrandTotal = offenseEntries.reduce((s,[,v]) => s+v, 0);
  const offenseMax = offenseEntries[0][1];
  const TOP_N = 10;

  const offenseTop = document.getElementById('offenseTop');
  offenseEntries.slice(0, TOP_N).forEach(([name, count]) => {
    const pct = (count / offenseGrandTotal * 100).toFixed(1);
    const barPct = (count / offenseMax * 100).toFixed(1);
    const row = document.createElement('div');
    row.className = 'offense-bar-row';
    row.innerHTML = `
      <div class="name">${name}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${barPct}%"></div></div>
      <div class="count"><strong>${count.toLocaleString()}</strong> (${pct}%)</div>
    `;
    offenseTop.appendChild(row);
  });

  const tbody = document.getElementById('offenseTableBody');
  offenseEntries.forEach(([name, count]) => {
    const pct = (count / offenseGrandTotal * 100).toFixed(1);
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${name}</td><td class="num">${count.toLocaleString()}</td><td class="num">${pct}%</td>`;
    tbody.appendChild(tr);
  });
}
</script>"""

OFFENSE_SECTION = """  <div class="section">
    <h2>Offense Type Breakdown</h2>
    <p class="trend-caption" style="margin-top:0;margin-bottom:16px;">All-time totals by offense category.</p>
    <div id="offenseTop"></div>
    <details class="offense-more">
      <summary>Show all offense types</summary>
      <table class="offense-table">
        <thead>
          <tr><th>Offense Type</th><th style="text-align:right;">Count</th><th style="text-align:right;">Share</th></tr>
        </thead>
        <tbody id="offenseTableBody"></tbody>
      </table>
    </details>
  </div>"""


def build_page(agency_name, county, agency_data, dataset_start, dataset_end, month_labels):
    slug_county = slugify(county)
    values = agency_data["monthly"]
    stats = compute_stats(month_labels, values)

    grid = build_full_grid(month_labels, values, dataset_end)
    end_year, end_month = dataset_end.split("-")

    status_class = "current" if agency_data["current"] else "stale"
    status_label = "Current" if agency_data["current"] else "Not current"

    if stats is None:
        body = BODY_NO_DATA
        body = body.replace("__DATASET_START_DISPLAY__", label_to_display(dataset_start))
        body = body.replace("__DATASET_END_DISPLAY__", label_to_display(dataset_end))
    else:
        offense_types = agency_data.get("offense_types", {})
        offense_section = OFFENSE_SECTION if offense_types else ""

        body = BODY_WITH_DATA
        body = body.replace("__TOTAL__", f"{stats['total']:,}")
        body = body.replace("__SUBMITTED_MONTHS__", str(agency_data["submitted_months"]))
        body = body.replace("__TOTAL_MONTHS__", str(agency_data["total_months"]))
        body = body.replace("__AVG__", f"{stats['avg']:,}")
        body = body.replace("__HIGHEST_VALUE__", f"{stats['highest']['value']:,}")
        body = body.replace("__HIGHEST_LABEL__", label_to_display(stats['highest']['label']))
        body = body.replace("__LOWEST_VALUE__", f"{stats['lowest']['value']:,}")
        body = body.replace("__LOWEST_LABEL__", label_to_display(stats['lowest']['label']))
        body = body.replace("__OFFENSE_SECTION__", offense_section)
        body = body.replace("__GRID_JS__", json.dumps(grid))
        body = body.replace("__DATASET_END_YEAR__", end_year)
        body = body.replace("__DATASET_END_MONTH__", str(int(end_month)))
        body = body.replace("__OFFENSE_JS__", json.dumps(offense_types))

    html = PAGE_TEMPLATE
    html = html.replace("__TITLE__", f"{agency_name} - FIBRS Data")
    html = html.replace("__COUNTY_SLUG__", slug_county)
    html = html.replace("__COUNTY__", county)
    html = html.replace("__AGENCY_NAME__", agency_name)
    html = html.replace("__DATASET_START_DISPLAY__", label_to_display(dataset_start))
    html = html.replace("__DATASET_END_DISPLAY__", label_to_display(dataset_end))
    html = html.replace("__STATUS_CLASS__", status_class)
    html = html.replace("__STATUS_LABEL__", status_label)
    html = html.replace("__BODY__", body)
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_json", help="Path to data.json produced by extract.py")
    parser.add_argument("-o", "--output-dir", default="agencies",
                         help="Folder to write agency pages into (default: agencies)")
    args = parser.parse_args()

    data_path = Path(args.data_json)
    if not data_path.exists():
        print(f"File not found: {data_path}")
        sys.exit(1)

    data = json.loads(data_path.read_text(encoding="utf-8"))
    meta = data["meta"]
    dataset_start = meta["dataset_start"]
    dataset_end = meta["dataset_end"]
    month_labels = meta["month_labels"]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written_files = set()
    written = 0
    for county, county_data in data["counties"].items():
        for agency_name, agency_data in county_data["agencies"].items():
            html = build_page(agency_name, county, agency_data,
                               dataset_start, dataset_end, month_labels)
            filename = slugify(agency_name) + ".html"
            (out_dir / filename).write_text(html, encoding="utf-8")
            written_files.add(filename)
            written += 1

    # Remove any leftover .html files from a previous run that no longer
    # correspond to an agency in this dataset (e.g. an agency that stopped
    # appearing in the source, or was renamed). Without this, stale pages
    # would silently accumulate forever across automated runs.
    removed = 0
    for existing in out_dir.glob("*.html"):
        if existing.name not in written_files:
            existing.unlink()
            removed += 1

    print(f"Wrote {written} agency pages to {out_dir.resolve()}")
    if removed:
        print(f"Removed {removed} stale page(s) no longer in the dataset.")


if __name__ == "__main__":
    main()
