#!/usr/bin/env python3
"""Render terminal-style SVG panels for the profile README.

Pulls live data from the GitHub API and writes self-contained SVGs into
assets/. Everything is committed to the repo, so the README never depends
on a third-party rendering service staying up.

Usage:
    python3 scripts/generate_panels.py          # live data (needs GITHUB_TOKEN)
    python3 scripts/generate_panels.py --mock   # offline sample data
"""

import base64
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

USER = os.environ.get("PROFILE_USER", "jitheender-ops")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
MOCK = "--mock" in sys.argv

# ---------------------------------------------------------------- palette --
BG = "#05090b"
PANEL = "#0a1411"
EDGE = "#1c3b32"
GREEN = "#34d399"
BRIGHT = "#8af7c8"
DIM = "#5f7d74"
TEXT = "#c8e6da"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

# Repos to show in the projects grid, in order. Edit this list to change the
# grid. Any slot left over is filled automatically from your top repos.
FEATURED = [
    "commerce-os",
    "resume-radar",
    "ai-editing-claud",
    "payment-recovery-engine",
]

# Fallback blurbs for repos with no description set on GitHub. Setting the
# description on the repo itself is better — it shows everywhere on GitHub.
DESCRIPTIONS = {
    "resume-radar": "Free 30-second ATS resume checker — instant score, concrete "
                    "fixes, and job-description keyword matching.",
    "payment-recovery-engine": "Recovers failed payments through automated retry "
                               "orchestration.",
}

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "HTML": "#e34c26", "CSS": "#563d7c", "Java": "#b07219", "C": "#555555",
    "C++": "#f34b7d", "Go": "#00ADD8", "Rust": "#dea584", "Shell": "#89e051",
    "Jupyter Notebook": "#DA5B0B", "Ruby": "#701516", "PHP": "#4F5D95",
}


def esc(value):
    """Escape text for XML content. Every dynamic string goes through this."""
    return escape(str(value))


# ------------------------------------------------------------------- data --
def tidy_location(value):
    """Capitalise an all-lowercase location, but leave "USA"/"São Paulo" alone."""
    if not value:
        return "—"
    return value.title() if value.islower() else value


def api(path, host="api.github.com"):
    req = urllib.request.Request(f"https://{host}{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-panels")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def graphql_contributions():
    """Total contributions in the last year. Returns None if unavailable."""
    if not TOKEN:
        return None
    query = {
        "query": "query($login:String!){user(login:$login){contributionsCollection"
                 "{contributionCalendar{totalContributions}}}}",
        "variables": {"login": USER},
    }
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps(query).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-panels",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
        return (body["data"]["user"]["contributionsCollection"]
                    ["contributionCalendar"]["totalContributions"])
    except Exception as exc:  # noqa: BLE001 - contributions are optional
        print(f"  contributions unavailable: {exc}")
        return None


def avatar_data_uri(url):
    """Fetch the avatar and inline it, so the SVG stays self-contained."""
    try:
        req = urllib.request.Request(f"{url}&s=200" if "?" in url else f"{url}?s=200")
        req.add_header("User-Agent", "profile-panels")
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        return "data:image/png;base64," + base64.b64encode(raw).decode()
    except Exception as exc:  # noqa: BLE001 - fall back to initials
        print(f"  avatar unavailable: {exc}")
        return None


def collect():
    if MOCK:
        return {
            "name": "Manapuram Jitheender Kumar", "login": USER,
            "bio": "B.Tech student building AI agents and full-stack apps",
            "location": "India", "followers": 0, "public_repos": 16,
            "created_at": "2025-08-22T03:05:50Z", "avatar": None,
            "stars": 0, "contributions": None,
            "languages": [("Python", 41.0), ("TypeScript", 30.0),
                          ("JavaScript", 18.0), ("HTML", 11.0)],
            "repos": [
                {"name": "commerce-os", "desc": "Seven AI agents running an online "
                 "business under a deterministic governance pipeline.",
                 "lang": "TypeScript", "stars": 0, "pct": 92},
                {"name": "resume-radar", "desc": "Free 30-second ATS resume checker "
                 "with instant scoring and keyword matching.",
                 "lang": "JavaScript", "stars": 0, "pct": 78},
                {"name": "ai-editing-claud", "desc": "Learns a reference video's "
                 "editing style and rebuilds the timeline in DaVinci Resolve.",
                 "lang": "Python", "stars": 0, "pct": 85},
                {"name": "payment-recovery-engine", "desc": "Recovers failed "
                 "payments through automated retry orchestration.",
                 "lang": "Python", "stars": 0, "pct": 71},
            ],
        }

    print(f"fetching profile for {USER}")
    user = api(f"/users/{USER}")
    repos = api(f"/users/{USER}/repos?per_page=100&type=owner&sort=updated")
    # Never surface private repositories, whatever the token can see.
    repos = [r for r in repos if not r.get("private") and not r.get("fork")]
    # The profile repo itself is plumbing, not a project worth featuring.
    repos = [r for r in repos if r["name"].lower() != USER.lower()]

    totals = {}
    for repo in repos:
        lang = repo.get("language")
        if lang:
            totals[lang] = totals.get(lang, 0) + 1
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:5]
    total_count = sum(count for _, count in ranked) or 1
    languages = [(lang, round(count * 100.0 / total_count, 1)) for lang, count in ranked]

    # Curated picks first, then auto-fill any remaining slots: a described repo
    # presents better than a bare name, then stars, then recency.
    by_name = {r["name"].lower(): r for r in repos}
    featured, seen = [], set()
    for name in FEATURED:
        repo = by_name.get(name.lower())
        if repo and repo["name"] not in seen:
            featured.append(repo)
            seen.add(repo["name"])

    auto = sorted(
        repos,
        key=lambda r: (
            bool(r.get("description")),
            r.get("stargazers_count", 0),
            r.get("pushed_at", ""),
        ),
        reverse=True,
    )
    for repo in auto:
        if len(featured) >= 4:
            break
        if repo["name"] not in seen:
            featured.append(repo)
            seen.add(repo["name"])
    featured = featured[:4]

    picks = []
    for repo in featured:
        pct = 0
        try:
            breakdown = api(f"/repos/{USER}/{repo['name']}/languages")
            if breakdown:
                pct = round(max(breakdown.values()) * 100.0 / sum(breakdown.values()))
        except Exception:  # noqa: BLE001 - ring is decorative
            pct = 0
        picks.append({
            "name": repo["name"],
            "desc": (repo.get("description")
                     or DESCRIPTIONS.get(repo["name"], "No description provided.")),
            "lang": repo.get("language") or "—",
            "stars": repo.get("stargazers_count", 0),
            "pct": pct,
        })

    return {
        "name": user.get("name") or USER,
        "login": USER,
        "bio": user.get("bio") or "",
        "location": tidy_location(user.get("location")),
        "followers": user.get("followers", 0),
        "public_repos": len(repos),
        "created_at": user.get("created_at"),
        "avatar": avatar_data_uri(user.get("avatar_url", "")),
        "stars": sum(r.get("stargazers_count", 0) for r in repos),
        "contributions": graphql_contributions(),
        "languages": languages,
        "repos": picks,
    }


# ------------------------------------------------------------------- chrome --
def defs():
    return f"""<defs>
  <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="2.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <linearGradient id="sweep" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{BRIGHT}" stop-opacity="0"/>
    <stop offset="50%" stop-color="{BRIGHT}" stop-opacity="0.55"/>
    <stop offset="100%" stop-color="{BRIGHT}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{GREEN}" stop-opacity="0.75"/>
    <stop offset="100%" stop-color="{GREEN}" stop-opacity="0.2"/>
  </linearGradient>
</defs>"""


def window(width, height, title):
    """Terminal window chrome: rounded frame, traffic lights, title bar."""
    dots = "".join(
        f'<circle cx="{22 + i * 18}" cy="21" r="5" fill="{c}" opacity="0.9"/>'
        for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f"))
    )
    return f"""<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="12"
    fill="{PANEL}" stroke="url(#edge)" stroke-width="1.5"/>
  <path d="M1 13 a12 12 0 0 1 12 -12 h{width - 26} a12 12 0 0 1 12 12 v29 h-{width - 2} z"
    fill="#081210"/>
  <line x1="1" y1="42" x2="{width - 1}" y2="42" stroke="{EDGE}" stroke-width="1"/>
  {dots}
  <text x="{width / 2}" y="26" fill="{DIM}" font-family="{MONO}" font-size="12"
    text-anchor="middle">{esc(title)}</text>"""


def svg_open(width, height):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">{defs()}'
            f'<rect width="{width}" height="{height}" fill="{BG}"/>')


def write(name, body):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body + "</svg>\n")
    print(f"  wrote assets/{name} ({os.path.getsize(path)} bytes)")


# ------------------------------------------------------------------ panels --
def banner(data):
    """Dot-matrix name plate.

    The letters are drawn as rectangles rather than text: ASCII art rendered
    as glyphs depends on whichever monospace font the viewer happens to have,
    and box-drawing characters smear badly when that font differs. Rectangles
    look identical in every renderer.
    """
    import pyfiglet
    # width= must exceed the rendered art or pyfiglet wraps onto a second block
    art = pyfiglet.Figlet(font="banner3", width=400).renderText(USER.split("-")[0].upper())
    lines = [ln.rstrip() for ln in art.splitlines() if ln.strip()]
    cols = max(len(ln) for ln in lines)

    width, top = 900, 44
    pitch = max(3, min(9, int(800 / cols)))  # shrink to fit long names
    cell = pitch - 1
    art_w, art_h = cols * pitch, len(lines) * pitch
    height = top + art_h + 60
    x0 = (width - art_w) / 2

    body = [svg_open(width, height)]
    body.append('<g filter="url(#glow)">')
    for row, line in enumerate(lines):
        col = 0
        while col < len(line):
            if line[col] != " ":
                run = col
                while run < len(line) and line[run] != " ":
                    run += 1
                # one rect per horizontal run keeps the file small
                body.append(
                    f'<rect x="{x0 + col * pitch:.0f}" y="{top + row * pitch}" '
                    f'width="{(run - col - 1) * pitch + cell}" height="{cell}" '
                    f'fill="{GREEN}" opacity="0.92"/>'
                )
                col = run
            else:
                col += 1
    body.append("</g>")

    tagline = data["bio"] or "Building things on the internet"
    body.append(
        f'<text x="450" y="{height - 28}" fill="{DIM}" font-family="{MONO}" '
        f'font-size="13" text-anchor="middle">{esc(tagline[:78])}</text>'
    )
    body.append(
        f'<rect x="0" y="0" width="{width}" height="6" fill="url(#sweep)" opacity="0.5">'
        f'<animate attributeName="y" values="0;{height};0" dur="7s" repeatCount="indefinite"/>'
        f'</rect>'
    )
    write("banner.svg", "".join(body))


def radar(x0, y0, cols=58, rows=19, size=10):
    """Dot-matrix dome, densest near the centre — the 'visual map' panel."""
    chars = " .:-=+*#%@"
    out = []
    for row in range(rows):
        line = []
        for col in range(cols):
            nx = (col - cols / 2) / (cols / 2)
            ny = (rows - row) / rows
            dist = math.sqrt(nx * nx + ny * ny)
            if dist > 1.0:
                line.append(" ")
                continue
            # deterministic sparsity so the pattern is stable between runs
            noise = (math.sin(col * 12.9898 + row * 78.233) * 43758.5453) % 1.0
            level = (1.0 - dist) * 9 * (0.55 + 0.45 * noise)
            line.append(chars[max(0, min(9, int(level)))])
        out.append(
            f'<text x="{x0}" y="{y0 + row * (size + 2)}" fill="{GREEN}" '
            f'font-family="{MONO}" font-size="{size}" xml:space="preserve" '
            f'opacity="{0.35 + 0.5 * (row / rows):.2f}">{esc("".join(line))}</text>'
        )
    return "".join(out)


def scan(data):
    width, height = 900, 372
    created = data.get("created_at")
    if created:
        start = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        active_days = (datetime.now(timezone.utc) - start).days
    else:
        active_days = "—"

    contributions = data["contributions"]
    rows = [
        ("Handle", f"@{data['login']}"),
        ("Role", "B.Tech CS Student"),
        ("Status", "Building | Learning | Shipping"),
        ("Languages", ", ".join(lang for lang, _ in data["languages"][:3]) or "—"),
        ("Location", data["location"]),
        ("Repositories", data["public_repos"]),
        ("Contributions", contributions if contributions is not None else "—"),
        ("Stars", data["stars"]),
        ("Followers", data["followers"]),
        ("Active Days", active_days),
        ("Contact", f"github.com/{data['login']}"),
    ]

    body = [svg_open(width, height)]
    body.append(window(width, height, f"{data['login']}@github ~ $ ./profile-scan --live"))

    # left: visual map
    body.append(f'<rect x="18" y="56" width="420" height="298" rx="8" fill="#07100e" '
                f'stroke="{EDGE}" stroke-width="1"/>')
    body.append(f'<text x="32" y="76" fill="{DIM}" font-family="{MONO}" font-size="10" '
                f'letter-spacing="1.5">VISUAL.MAP</text>')
    body.append(radar(42, 96))
    body.append(f'<rect x="19" y="56" width="418" height="3" fill="url(#sweep)">'
                f'<animate attributeName="y" values="56;350;56" dur="4.5s" '
                f'repeatCount="indefinite"/></rect>')

    # right: system.info
    body.append(f'<rect x="454" y="56" width="428" height="298" rx="8" fill="#07100e" '
                f'stroke="{EDGE}" stroke-width="1"/>')
    body.append(f'<text x="470" y="76" fill="{DIM}" font-family="{MONO}" font-size="10" '
                f'letter-spacing="1.5">SYSTEM.INFO</text>')
    for index, (label, value) in enumerate(rows):
        y = 100 + index * 23
        body.append(f'<text x="470" y="{y}" fill="{DIM}" font-family="{MONO}" '
                    f'font-size="11">{esc(label)}</text>')
        body.append(f'<text x="866" y="{y}" fill="{TEXT}" font-family="{MONO}" '
                    f'font-size="11" text-anchor="end">{esc(value)}</text>')
        body.append(f'<line x1="470" y1="{y + 6}" x2="866" y2="{y + 6}" '
                    f'stroke="{EDGE}" stroke-width="0.5" opacity="0.5"/>')
    write("scan.svg", "".join(body))


def hero(data):
    width, height = 900, 168
    body = [svg_open(width, height)]
    body.append(f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="14" '
                f'fill="{PANEL}" stroke="url(#edge)" stroke-width="1.5"/>')

    if data["avatar"]:
        body.append('<clipPath id="av"><circle cx="86" cy="84" r="46"/></clipPath>')
        body.append(f'<image x="40" y="38" width="92" height="92" href="{data["avatar"]}" '
                    f'clip-path="url(#av)"/>')
    else:
        initials = "".join(part[0] for part in data["name"].split()[:2]).upper()
        body.append(f'<circle cx="86" cy="84" r="46" fill="#0d1f1a" stroke="{GREEN}"/>')
        body.append(f'<text x="86" y="93" fill="{GREEN}" font-family="{MONO}" '
                    f'font-size="28" text-anchor="middle">{esc(initials)}</text>')
    body.append(f'<circle cx="86" cy="84" r="47" fill="none" stroke="{GREEN}" '
                f'stroke-width="1.5" opacity="0.7"/>')

    body.append(f'<text x="164" y="66" fill="{DIM}" font-family="{MONO}" font-size="12">'
                f'@{esc(data["login"])}</text>')
    body.append(f'<text x="164" y="98" fill="{BRIGHT}" font-family="{MONO}" '
                f'font-size="26" filter="url(#glow)">{esc(data["name"])}</text>')

    chips = [lang for lang, _ in data["languages"][:4]]
    x = 164
    for chip in chips:
        chip_w = 12 + len(chip) * 7
        body.append(f'<rect x="{x}" y="114" width="{chip_w}" height="22" rx="11" '
                    f'fill="#0d1f1a" stroke="{EDGE}"/>')
        body.append(f'<text x="{x + chip_w / 2}" y="129" fill="{TEXT}" '
                    f'font-family="{MONO}" font-size="10" text-anchor="middle">'
                    f'{esc(chip)}</text>')
        x += chip_w + 8

    stats = [("repos", data["public_repos"]), ("stars", data["stars"]),
             ("followers", data["followers"])]
    for index, (label, value) in enumerate(stats):
        y = 62 + index * 32
        body.append(f'<text x="866" y="{y}" fill="{BRIGHT}" font-family="{MONO}" '
                    f'font-size="17" text-anchor="end">{esc(value)}</text>')
        body.append(f'<text x="866" y="{y + 13}" fill="{DIM}" font-family="{MONO}" '
                    f'font-size="9" text-anchor="end">{esc(label.upper())}</text>')
    write("hero.svg", "".join(body))


def wrap(text, limit, max_lines=2):
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > limit:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        # mark the cut so a clipped description doesn't read as a full sentence
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: limit - 1].rstrip(" ,.;:") + "…"
    return lines


def projects(data):
    width, height = 900, 300
    body = [svg_open(width, height)]
    body.append(window(width, height, f"{data['login']}@github ~ $ ls --featured"))

    for index, repo in enumerate(data["repos"][:4]):
        col, row = index % 2, index // 2
        x, y = 18 + col * 434, 56 + row * 118
        body.append(f'<rect x="{x}" y="{y}" width="430" height="112" rx="8" '
                    f'fill="#07100e" stroke="{EDGE}" stroke-width="1"/>')
        body.append(f'<text x="{x + 16}" y="{y + 26}" fill="{BRIGHT}" '
                    f'font-family="{MONO}" font-size="14">{esc(repo["name"])}</text>')
        for line_index, line in enumerate(wrap(repo["desc"], 44)):
            body.append(f'<text x="{x + 16}" y="{y + 48 + line_index * 15}" fill="{DIM}" '
                        f'font-family="{MONO}" font-size="10.5">{esc(line)}</text>')

        color = LANG_COLORS.get(repo["lang"], GREEN)
        body.append(f'<circle cx="{x + 21}" cy="{y + 92}" r="4" fill="{color}"/>')
        body.append(f'<text x="{x + 31}" y="{y + 96}" fill="{TEXT}" font-family="{MONO}" '
                    f'font-size="10">{esc(repo["lang"])}</text>')
        body.append(f'<text x="{x + 130}" y="{y + 96}" fill="{DIM}" font-family="{MONO}" '
                    f'font-size="10">★ {esc(repo["stars"])}</text>')

        # donut ring showing the primary language's share of the repo
        pct = max(0, min(100, repo["pct"]))
        cx, cy, r = x + 386, y + 56, 24
        circumference = 2 * math.pi * r
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#12241f" '
                    f'stroke-width="6"/>')
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
                    f'stroke-width="6" stroke-linecap="round" '
                    f'stroke-dasharray="{circumference * pct / 100:.1f} {circumference:.1f}" '
                    f'transform="rotate(-90 {cx} {cy})"/>')
        body.append(f'<text x="{cx}" y="{cy + 4}" fill="{TEXT}" font-family="{MONO}" '
                    f'font-size="11" text-anchor="middle">{esc(pct)}%</text>')
    write("projects.svg", "".join(body))


def main():
    data = collect()
    print("rendering panels")
    banner(data)
    hero(data)
    scan(data)
    projects(data)
    print("done")


if __name__ == "__main__":
    main()
