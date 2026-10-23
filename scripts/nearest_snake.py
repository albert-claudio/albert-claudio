#!/usr/bin/env python3
"""Generate a classic GitHub Snake with safe shortcuts toward nearby contributions."""
import json
import os
from collections import deque
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

USER = "albert-claudio"
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
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Content-Type": "application/json",
            "User-Agent": "github-classic-snake",
        },
    )
    with urlopen(request, timeout=30) as response:
        data = json.load(response)
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [[day["contributionCount"] for day in week["contributionDays"]] for week in weeks]


def cycle_path(w):
    """Safety circuit covering every cell; shortcuts preserve its ordering."""
    assert w >= 2 and w % 2 == 0
    path = [(0, y) for y in range(7)]
    for x in range(1, w):
        if x % 2:
            path.extend((x, y) for y in range(6, 0, -1))
        else:
            path.extend((x, y) for y in range(1, 7))
    path.append((w - 1, 0))
    path.extend((x, 0) for x in range(w - 2, 0, -1))
    assert len(path) == w * 7 and len(set(path)) == len(path)
    assert all(abs(a[0]-b[0]) + abs(a[1]-b[1]) == 1
               for a, b in zip(path, path[1:] + path[:1]))
    return path


def neighbors(p, w):
    x, y = p
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        xx, yy = x + dx, y + dy
        if 0 <= xx < w and 0 <= yy < 7:
            yield (xx, yy)


def update_body(body, new, ate):
    updated = deque(body)
    updated.appendleft(new)
    if not ate:
        updated.pop()
    return updated


def safe_moves(body, positions, food, w):
    """Only advance through free cycle-order space; never cross the body."""
    head = body[0]
    hi, ti = positions[head], positions[body[-1]]
    n = w * 7
    to_tail = (ti - hi) % n
    if len(body) == 1:
        to_tail = n
    occupied = set(body)
    for pos in neighbors(head, w):
        if len(body) > 1 and pos == body[1]:
            continue
        eaten = pos in food
        delta = (positions[pos] - hi) % n
        # Limiting large skips also prevents the first move from trapping a
        # freshly grown two-cell snake against its own neck.
        if not 0 < delta <= min(to_tail - (1 if eaten else 0), n // 2):
            continue
        if pos in (occupied if eaten else occupied - {body[-1]}):
            continue
        yield pos


def find_route(grid):
    actual_w = len(grid)
    w = actual_w if actual_w % 2 == 0 else actual_w + 1
    cycle = cycle_path(w)
    indices = {p: i for i, p in enumerate(cycle)}
    food = {(x, y) for x, col in enumerate(grid) for y, count in enumerate(col) if count}
    original_food = set(food)
    head = (0, 0)
    body = deque([head])
    route = [head]
    length_at_step = [1]
    eaten_at = {}
    if head in food:
        food.remove(head)
        eaten_at[head] = 0
    last_meal_step = 0
    limit = max(2000, len(cycle) * 20)

    for step in range(limit):
        if not food:
            break
        candidates = list(safe_moves(body, indices, food, w))
        if not candidates:
            raise RuntimeError("Safety invariant failed: no legal move")
        previous_dir = (
            (body[0][0]-body[1][0], body[0][1]-body[1][1])
            if len(body) > 1 else None
        )

        def rank(p):
            distance_to_tail = (indices[body[-1]] - indices[p]) % len(cycle)
            if len(body) == 1:
                distance_to_tail = len(cycle)
            options = []
            for f in food:
                clockwise = (indices[f] - indices[p]) % len(cycle)
                spatial = abs(p[0]-f[0]) + abs(p[1]-f[1])
                penalty = 0 if clockwise < distance_to_tail else 10
                options.append(spatial + clockwise * 0.014 + penalty)
            best = min(options)
            direction = (p[0]-head[0], p[1]-head[1])
            turned = previous_dir is not None and direction != previous_dir
            distance_forward = (indices[p]-indices[head]) % len(cycle)
            return (0 if p in food else 1, best,
                    0 if turned else 1, distance_forward, p[0], p[1])

        # If a shortcut repeatedly skips food, move along the guaranteed
        # safety circuit until eating again. No restart and no blind zigzag.
        if step - last_meal_step >= len(cycle):
            next_position = cycle[(indices[head]+1) % len(cycle)]
            if next_position not in candidates:
                raise RuntimeError("Safety circuit continuation unavailable")
        else:
            next_position = min(candidates, key=rank)

        ate = next_position in food
        body = update_body(body, next_position, ate)
        route.append(next_position)
        length_at_step.append(len(body))
        if ate:
            food.remove(next_position)
            eaten_at[next_position] = len(route)-1
            last_meal_step = step + 1
        head = next_position
    else:
        raise RuntimeError(f"Safe route reached its limit, {len(food)} uneaten cells")

    assert not food and set(eaten_at) == original_food

    # Only after ALL food has been eaten, deliberately hit the body.
    # A 2x2 square provides a real Snake-style self-collision, no reversal.
    for _ in range(len(cycle) * 2):
        head = body[0]
        candidates = []
        for p in neighbors(head, w):
            if len(body) > 1 and p == body[1]:
                continue
            if p in list(body)[:-1]:
                route.append(p)
                length_at_step.append(len(body))
                return route, length_at_step, eaten_at, w, True
            for a in neighbors(p, w):
                if a == head or abs(a[0]-head[0])+abs(a[1]-head[1]) != 2:
                    continue
                for b in neighbors(a, w):
                    if b == p or b not in set(neighbors(head, w)):
                        continue
                    sim = deque(body)
                    valid = True
                    for pt in (p, a, b):
                        if pt in list(sim)[:-1]:
                            valid = False
                            break
                        sim = update_body(sim, pt, False)
                    if valid and head in list(sim)[:-1]:
                        candidates.append((p, a, b, head))
        if candidates:
            turn = min(candidates)
            for pt in turn[:3]:
                body = update_body(body, pt, False)
                route.append(pt)
                length_at_step.append(len(body))
            route.append(turn[3])
            length_at_step.append(len(body))
            return route, length_at_step, eaten_at, w, True

        next_position = cycle[(indices[head]+1) % len(cycle)]
        if next_position not in list(safe_moves(body, indices, set(), w)):
            raise RuntimeError("No safe continuation before final collision")
        body = update_body(body, next_position, False)
        route.append(next_position)
        length_at_step.append(len(body))
    raise RuntimeError("Unable to arrange final self-collision")


def make_svg(grid, route, lengths, eaten_at, w, dark):
    pitch, cell, pad = 13, 10, 17
    width = pad * 2 + (w-1)*pitch + cell
    height = pad * 2 + 6*pitch + cell
    palette = (["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"] if dark
               else ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"])
    snake = "#65e6fc"
    frames = len(route)
    timestep = 0.095
    duration = (frames - 1) * timestep + 0.9
    keys = [(i*timestep)/duration for i in range(frames)] + [1.0]
    times = ";".join(f"{t:.7f}" for t in keys)
    dur = f"{duration:.3f}s"

    def xy(p):
        return pad + p[0]*pitch + cell/2, pad + p[1]*pitch + cell/2

    points = [xy(p) for p in route]
    path = " ".join(("M" if i == 0 else "L")+f"{x:g},{y:g}"
                    for i, (x,y) in enumerate(points))
    far_gap = (frames + len(eaten_at) + 30)*pitch
    dashes = [ln*pitch for ln in lengths]
    offsets = [dashes[i] - i*pitch for i in range(frames)]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Snake eats nearby GitHub contributions, grows, and crashes at end">',
        '<title>Snake — GitHub contributions</title>',
    ]
    for x,col in enumerate(grid):
        for y,num in enumerate(col):
            lvl = 0 if num == 0 else 1 if num < 3 else 2 if num < 6 else 3 if num < 10 else 4
            xx, yy = pad+x*pitch, pad+y*pitch
            parts.append(f'<rect x="{xx}" y="{yy}" width="{cell}" height="{cell}" rx="2" fill="{palette[lvl]}">')
            if (x,y) in eaten_at:
                moment = keys[eaten_at[(x,y)]]
                parts.append(f'<animate attributeName="opacity" values="1;0;0" keyTimes="0;{max(.0000001,moment):.7f};1" calcMode="discrete" dur="{dur}" repeatCount="indefinite"/>')
            parts.append('</rect>')

    parts += [
        f'<path d="{escape(path, quote=True)}" fill="none" stroke="{snake}" stroke-width="8.4" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="{dashes[0]} {far_gap}" stroke-dashoffset="{offsets[0]}">',
        f'<animate attributeName="stroke-dasharray" values="{";".join(f"{v:g} {far_gap:g}" for v in dashes+[dashes[-1]])}" keyTimes="{times}" calcMode="discrete" dur="{dur}" repeatCount="indefinite"/>',
        f'<animate attributeName="stroke-dashoffset" values="{";".join(f"{v:g}" for v in offsets+[offsets[-1]])}" keyTimes="{times}" calcMode="linear" dur="{dur}" repeatCount="indefinite"/>',
        '</path>',
        f'<circle r="4.5" fill="{snake}" cx="{points[0][0]:g}" cy="{points[0][1]:g}">',
        f'<animate attributeName="cx" values="{";".join(f"{p[0]:g}" for p in points+[points[-1]])}" keyTimes="{times}" dur="{dur}" calcMode="linear" repeatCount="indefinite"/>',
        f'<animate attributeName="cy" values="{";".join(f"{p[1]:g}" for p in points+[points[-1]])}" keyTimes="{times}" dur="{dur}" calcMode="linear" repeatCount="indefinite"/>',
        f'<animate attributeName="fill" values="{snake};{snake};#ff6b6b;#ff6b6b" keyTimes="0;{keys[-2]:.7f};{min(.9999999,keys[-2]+.0000001):.7f};1" dur="{dur}" repeatCount="indefinite"/>',
        '</circle>', '</svg>',
    ]
    return "\n".join(parts) + "\n"


def main():
    grid = get_grid()
    route, lengths, eaten, width, crashed = find_route(grid)
    out = Path("dist")
    out.mkdir(exist_ok=True)
    for dark, filename in ((False,"github-snake.svg"),(True,"github-snake-dark.svg")):
        (out / filename).write_text(
            make_svg(grid,route,lengths,eaten,width,dark),encoding="utf-8"
        )
    print(f"SUCCESS: {len(eaten)} food squares, {len(route)} steps, final collision={crashed}",flush=True)


if __name__ == "__main__":
    main()
