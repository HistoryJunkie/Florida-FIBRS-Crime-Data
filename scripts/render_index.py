#!/usr/bin/env python3
"""
render_index.py

Builds index.html: a county-by-county directory of every FIBRS-reporting
agency, each showing a Current/Not Current flag, months submitted out of
the dataset's total window, and an all-time offense total. Agency names
link out to their detail page under agencies/<slug>.html.

USAGE
    python render_index.py data.json -o index.html

Reads only data.json (produced by extract.py). Does not touch the source
Excel file or any other page.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ALL_FLORIDA_COUNTIES = [
    "Alachua", "Baker", "Bay", "Bradford", "Brevard", "Broward", "Calhoun",
    "Charlotte", "Citrus", "Clay", "Collier", "Columbia", "DeSoto", "Dixie",
    "Duval", "Escambia", "Flagler", "Franklin", "Gadsden", "Gilchrist",
    "Glades", "Gulf", "Hamilton", "Hardee", "Hendry", "Hernando", "Highlands",
    "Hillsborough", "Holmes", "Indian River", "Jackson", "Jefferson",
    "Lafayette", "Lake", "Lee", "Leon", "Levy", "Liberty", "Madison",
    "Manatee", "Marion", "Martin", "Miami-Dade", "Monroe", "Nassau",
    "Okaloosa", "Okeechobee", "Orange", "Osceola", "Palm Beach", "Pasco",
    "Pinellas", "Polk", "Putnam", "Santa Rosa", "Sarasota", "Seminole",
    "St. Johns", "St. Lucie", "Sumter", "Suwannee", "Taylor", "Union",
    "Volusia", "Wakulla", "Walton", "Washington",
]

# Counties with more than this many agencies are collapsed by default so
# the page doesn't open with a huge wall of rows for Miami-Dade, Pinellas, etc.
COLLAPSE_THRESHOLD = 6

AGENCIES_DIR = "agencies"  # detail pages live in this subfolder, sibling to index.html


def slugify(name):
    s = name.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def month_label_to_display(label):
    """'2026-07' -> 'July 2026'"""
    year, month = label.split("-")
    names = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]
    return f"{names[int(month)]} {year}"


def render_agency_row(name, info):
    slug = slugify(name)
    status_class = "current" if info["current"] else "stale"
    status_label = "Current" if info["current"] else "Not current"
    return f"""      <div class="agency-row">
        <span class="status-dot {status_class}" title="{status_label}"></span>
        <a class="agency-name" href="{AGENCIES_DIR}/{slug}.html">{name}</a>
        <span class="agency-stats">
          <span class="status-label {status_class}">{status_label}</span>
          <span class="sep">-</span>
          {info['submitted_months']} of {info['total_months']} months submitted
          <span class="sep">-</span>
          {info['total_offenses']:,} offenses
        </span>
      </div>"""


def render_county_section(county, county_data):
    agencies = county_data.get("agencies", {}) if county_data else {}
    slug = slugify(county)
    count = len(agencies)

    if count == 0:
        return f"""<section class="county-group" id="county-{slug}">
  <details open>
    <summary>
      <span class="county-name">{county} County</span>
      <span class="county-meta">No FIBRS-reporting agencies found in this dataset</span>
    </summary>
  </details>
</section>"""

    current_count = sum(1 for a in agencies.values() if a["current"])
    total_offenses = sum(a["total_offenses"] for a in agencies.values())
    details_attrs = " open" if count <= COLLAPSE_THRESHOLD else ""

    rows = "\n".join(
        render_agency_row(name, info)
        for name, info in sorted(agencies.items())
    )

    return f"""<section class="county-group" id="county-{slug}">
  <details{details_attrs}>
    <summary>
      <span class="county-name">{county} County</span>
      <span class="county-meta">{count} agenc{"y" if count == 1 else "ies"} - {current_count} current - {total_offenses:,} offenses all-time</span>
    </summary>
    <div class="agency-list">
{rows}
    </div>
  </details>
</section>"""


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Florida FIBRS Crime Data - All Agencies</title>
<style>
  :root{
    --bg:#0d1117;
    --panel:#161b22;
    --border:#30363d;
    --text:#c9d1d9;
    --muted:#8b949e;
    --accent:#58a6ff;
    --good:#39d353;
    --bad:#f85149;
  }
  *{box-sizing:border-box;}
  html{scroll-behavior:smooth;}
  body{
    margin:0;
    background:var(--bg);
    color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    padding:clamp(20px,4vw,40px) clamp(44px,9vw,72px) clamp(20px,4vw,40px) clamp(12px,3vw,16px);
  }
  .page-title{
    max-width:900px;
    margin:0 auto clamp(14px,2.5vw,18px);
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:16px;
  }
  .page-title .titles{flex:1;min-width:0;}
  .page-title h1{
    font-size:clamp(15px,3.6vw,18px);
    font-weight:600;
    margin:0 0 4px;
  }
  .page-title p{
    font-size:clamp(11px,2.6vw,12px);
    color:var(--muted);
    margin:0;
  }
  .page-title .about-link{
    flex-shrink:0;
    color:var(--accent);
    text-decoration:none;
    font-size:13px;
    font-weight:600;
    border:1px solid var(--border);
    padding:6px 12px;
    border-radius:6px;
    white-space:nowrap;
  }
  .page-title .about-link:hover{
    background:rgba(88,166,255,0.1);
  }

  .content{max-width:900px;margin:0 auto;}

  .search-wrap{margin-bottom:20px;}
  .search-wrap input{
    width:100%;
    background:var(--panel);
    border:1px solid var(--border);
    border-radius:6px;
    color:var(--text);
    padding:10px 14px;
    font-size:14px;
    font-family:inherit;
  }
  .search-wrap input:focus{outline:1px solid var(--accent);}
  .search-wrap input::placeholder{color:var(--muted);}
  .search-count{font-size:11px;color:var(--muted);margin-top:6px;}

  .county-group{scroll-margin-top:16px;margin-bottom:10px;}
  .county-group details{
    background:var(--panel);
    border:1px solid var(--border);
    border-radius:6px;
  }
  .county-group summary{
    cursor:pointer;
    list-style:none;
    padding:14px 18px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    flex-wrap:wrap;
    gap:6px 14px;
  }
  .county-group summary::-webkit-details-marker{display:none;}
  .county-group summary::before{
    content:">";
    display:inline-block;
    margin-right:8px;
    color:var(--muted);
    transition:transform 0.15s ease;
  }
  .county-group details[open] summary::before{
    transform:rotate(90deg);
  }
  .county-name{font-size:14.5px;font-weight:700;color:var(--text);}
  .county-meta{font-size:11.5px;color:var(--muted);}

  .agency-list{
    padding:0 18px 14px;
    border-top:1px solid var(--border);
  }
  .agency-row{
    display:flex;
    align-items:baseline;
    flex-wrap:wrap;
    gap:4px 10px;
    padding:9px 0;
    border-bottom:1px solid #1c2128;
  }
  .agency-row:last-child{border-bottom:none;}
  .status-dot{
    width:8px;height:8px;border-radius:50%;
    flex-shrink:0;
    align-self:center;
  }
  .status-dot.current{background:var(--good);}
  .status-dot.stale{background:var(--bad);}
  .agency-name{
    color:var(--accent);
    text-decoration:none;
    font-size:13.5px;
    font-weight:600;
  }
  .agency-name:hover{text-decoration:underline;}
  .agency-stats{
    font-size:12px;
    color:var(--muted);
    white-space:normal;
  }
  .status-label{font-weight:600;}
  .status-label.current{color:var(--good);}
  .status-label.stale{color:var(--bad);}
  .agency-stats .sep{color:var(--border);margin:0 2px;}

  .agency-row.hidden{display:none;}
  .county-group.hidden{display:none;}

  .alpha-nav{
    position:fixed;top:0;right:0;bottom:0;
    width:clamp(34px,7vw,48px);
    display:flex;flex-direction:column;
    background:var(--panel);
    border-left:1px solid var(--border);
    z-index:100;
    padding:10px 0;
  }
  .alpha-nav button{
    appearance:none;border:none;background:none;
    color:var(--border);
    font-size:clamp(10px,1.7vh,14px);
    font-family:inherit;line-height:1;
    flex:1 1 0;min-height:0;width:100%;
    display:flex;align-items:center;justify-content:center;
    cursor:default;
    transition:background 0.12s ease,color 0.12s ease;
  }
  .alpha-nav button.active{color:var(--muted);cursor:pointer;font-weight:600;}
  .alpha-nav button.active:hover{color:var(--accent);background:rgba(88,166,255,0.08);}
  .alpha-nav button.active:active{background:rgba(88,166,255,0.18);}
  .alpha-nav button.current{color:var(--accent);background:rgba(88,166,255,0.12);}

  @media (max-width:600px){
    body{padding:20px 40px 20px 12px;}
    .agency-stats{font-size:11px;}
  }
</style>
</head>
<body>

<div class="page-title">
  <div class="titles">
    <h1>Florida FIBRS Crime Data - All Agencies</h1>
    <p>__META_LINE__</p>
  </div>
  <a class="about-link" href="readme.html">About This Data</a>
</div>

<div class="content">
  <div class="search-wrap">
    <input type="text" id="searchBox" placeholder="Search by agency or county name...">
    <div class="search-count" id="searchCount"></div>
  </div>

  <div id="countyList">
__COUNTY_SECTIONS__
  </div>
</div>

<nav class="alpha-nav" id="alphaNav" aria-label="Jump to county"></nav>

<script>
// ---- sticky A-Z nav (by county) ----
const groups = Array.from(document.querySelectorAll('.county-group'));
const lettersPresent = new Set(groups.map(g => g.querySelector('.county-name').textContent.trim()[0].toUpperCase()));

const alphaNav = document.getElementById('alphaNav');
const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
alphabet.forEach(letter => {
  const btn = document.createElement('button');
  btn.textContent = letter;
  if(lettersPresent.has(letter)){
    btn.classList.add('active');
    btn.addEventListener('click', () => {
      const target = groups.find(g => g.querySelector('.county-name').textContent.trim()[0].toUpperCase() === letter);
      if(target) target.scrollIntoView({behavior:'smooth', block:'start'});
    });
  }
  alphaNav.appendChild(btn);
});

function updateCurrentLetter(){
  let current = null;
  for(const g of groups){
    if(g.getBoundingClientRect().top <= 80){
      current = g;
    } else {
      break;
    }
  }
  alphaNav.querySelectorAll('button').forEach(b => b.classList.remove('current'));
  if(current){
    const letter = current.querySelector('.county-name').textContent.trim()[0].toUpperCase();
    const idx = alphabet.indexOf(letter);
    if(idx >= 0) alphaNav.children[idx].classList.add('current');
  }
}
document.addEventListener('scroll', updateCurrentLetter, {passive:true});
updateCurrentLetter();

// ---- search / filter ----
const searchBox = document.getElementById('searchBox');
const searchCount = document.getElementById('searchCount');
const allRows = Array.from(document.querySelectorAll('.agency-row'));

searchBox.addEventListener('input', () => {
  const q = searchBox.value.trim().toLowerCase();

  if(q === ''){
    groups.forEach(g => {
      g.classList.remove('hidden');
      const d = g.querySelector('details');
      if(d && d.dataset.wasOpen === 'true') d.open = true;
    });
    allRows.forEach(r => r.classList.remove('hidden'));
    searchCount.textContent = '';
    return;
  }

  let visibleCount = 0;
  groups.forEach(g => {
    const countyName = g.querySelector('.county-name').textContent.toLowerCase();
    const rows = Array.from(g.querySelectorAll('.agency-row'));
    const countyMatches = countyName.includes(q);
    let anyRowMatches = false;

    rows.forEach(r => {
      const name = r.querySelector('.agency-name').textContent.toLowerCase();
      const match = countyMatches || name.includes(q);
      r.classList.toggle('hidden', !match);
      if(match){ anyRowMatches = true; visibleCount++; }
    });

    const groupVisible = countyMatches || anyRowMatches;
    g.classList.toggle('hidden', !groupVisible);

    const d = g.querySelector('details');
    if(d && groupVisible){
      if(d.dataset.wasOpen === undefined) d.dataset.wasOpen = String(d.open);
      d.open = true;
    } else if(d && d.dataset.wasOpen !== undefined){
      d.open = d.dataset.wasOpen === 'true';
    }
  });

  searchCount.textContent = `${visibleCount} agenc${visibleCount === 1 ? 'y' : 'ies'} match`;
});
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_json", help="Path to data.json produced by extract.py")
    parser.add_argument("-o", "--output", default="index.html",
                         help="Output HTML path (default: index.html)")
    args = parser.parse_args()

    data_path = Path(args.data_json)
    if not data_path.exists():
        print(f"File not found: {data_path}")
        sys.exit(1)

    data = json.loads(data_path.read_text(encoding="utf-8"))
    meta = data["meta"]
    counties = data["counties"]

    total_agencies = sum(len(c["agencies"]) for c in counties.values())
    total_current = sum(
        1 for c in counties.values() for a in c["agencies"].values() if a["current"]
    )

    meta_line = (
        f"Data through {month_label_to_display(meta['dataset_end'])} "
        f"({meta['total_months']} months since January 2021) - "
        f"{total_agencies} agencies across Florida's 67 counties - "
        f"{total_current} currently reporting"
    )

    sections = "\n".join(
        render_county_section(county, counties.get(county))
        for county in ALL_FLORIDA_COUNTIES
    )

    html = PAGE_TEMPLATE
    html = html.replace("__META_LINE__", meta_line)
    html = html.replace("__COUNTY_SECTIONS__", sections)

    out_path = Path(args.output)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path.resolve()}")
    print(f"{len(ALL_FLORIDA_COUNTIES)} county sections, {total_agencies} agencies, "
          f"{total_current} currently reporting.")


if __name__ == "__main__":
    main()
