#!/usr/bin/env python3
"""Generate a nearest-first contribution snake as animated SVG, without extra dependencies."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from html import escape

USER = "albert-claudio"
TOKEN = os.environ["GH_TOKEN"]
QUERY = """query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { contributionCount } }
      }
    }
  }
}"""

def get_grid():
    data = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    request = Request("https://api.github.com/graphql", data=data, headers={
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "nearest-contribution-snake",
    })
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [[day["contributionCount"] for day in week["contributionDays"]] for week in weeks]

def make_route(grid):
    width = len(grid)
    targets = {(x, y) for x, week in enumerate(grid) for y, count in enumerate(week) if count}
    current = (0, 0)
    points = [current]
    eaten_at = {}
    if current in targets:
        eaten_at[current] = 0
        targets.remove(current)
    # Each move is just one neighboring square. Crossed-over contributions are eaten too.
    # Favor the nearest remaining square, then lower horizontal travel, then the earliest week.
    while targets:
        tx, ty = min(targets, key=lambda p: (
            abs(p[0] - current[0]) + abs(p[1] - current[1]),
            abs(p[0] - current[0]),
            p[0], p[1],
        ))
        while current != (tx, ty):
            x, y = current
            if y != ty:
                y += 1 if ty > y else -1
            else:
                x += 1 if tx > x else -1
            current = (x, y)
            points.append(current)
            if current in targets:
                targets.remove(current)
                eaten_at[current] = len(points) - 1
    return points, eaten_at

def svg(grid, points, eaten_at, dark):
    width = len(grid)
    pitch, box, pad = 13, 10, 17
    w, h = pad * 2 + (width - 1) * pitch + box, pad * 2 + 6 * pitch + box
    duration = max(16, (len(points) - 1) * 0.095)
    duration_string = f"{duration:.2f}s"
    palette = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"] if dark else [
        "#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"
    ]
    snake = "#65e6fc"
    coord = lambda p: (pad + p[0] * pitch + box / 2, pad + p[1] * pitch + box / 2)
    path = " ".join(("M" if i == 0 else "L") + f"{coord(p)[0]:g},{coord(p)[1]:g}" for i, p in enumerate(points))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Snake eating GitHub contributions, nearest first">',
        '<title>GitHub contributions snake — nearest first</title>',
    ]
    steps = max(1, len(points) - 1)
    for x, week in enumerate(grid):
        for y, count in enumerate(week):
            level = 0 if count == 0 else (1 if count < 3 else 2 if count < 6 else 3 if count < 10 else 4)
            xx, yy = pad + x * pitch, pad + y * pitch
            parts.append(f'<rect x="{xx}" y="{yy}" width="{box}" height="{box}" rx="2" fill="{palette[level]}">')
            if (x, y) in eaten_at:
                t = min(0.999, eaten_at[(x, y)] / steps)
                t2 = min(1, t + 0.0001)
                parts.append(f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;{t:.6f};{t2:.6f};1" dur="{duration_string}" repeatCount="indefinite"/>')
            parts.append('</rect>')
    # Delayed segments follow the same continuous route; no long-distance jumps to targets.
    for i, radius in [(3, 3.7), (2, 4.0), (1, 4.4), (0, 5.1)]:
        delay = i * 0.095
        parts.append(f'<circle r="{radius}" fill="{snake}" opacity="{0.66 if i else 1}">'
                     f'<animateMotion path="{escape(path, quote=True)}" dur="{duration_string}" begin="{delay:.3f}s" repeatCount="indefinite" fill="freeze" calcMode="linear"/>'
                     '</circle>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"

def main():
    grid = get_grid()
    points, eaten_at = make_route(grid)
    out = Path("dist")
    out.mkdir(exist_ok=True)
    (out / "github-snake.svg").write_text(svg(grid, points, eaten_at, False), encoding="utf-8")
    (out / "github-snake-dark.svg").write_text(svg(grid, points, eaten_at, True), encoding="utf-8")
    print(f"Generated two themes, {len(eaten_at)} contributions consumed in {len(points)-1} steps")

if __name__ == "__main__":
    main()
