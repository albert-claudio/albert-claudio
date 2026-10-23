#!/usr/bin/env python3
"""Generate a classic Snake-style GitHub contribution animation (pure Python SVG)."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from html import escape

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
        response_data = json.load(response)
    if response_data.get("errors"):
        raise RuntimeError(str(response_data["errors"]))
    weeks = response_data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [[day["contributionCount"] for day in week["contributionDays"]] for week in weeks]


from collections import deque
from random import Random

DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))


def adjacent(p, width):
    for dx, dy in DIRECTIONS:
        q = (p[0] + dx, p[1] + dy)
        if 0 <= q[0] < width and 0 <= q[1] < 7:
            yield q


def distances(start, blocked, width):
    result = {start: 0}
    pending = deque([start])
    while pending:
        current = pending.popleft()
        for pos in adjacent(current, width):
            if pos not in blocked and pos not in result:
                result[pos] = result[current] + 1
                pending.append(pos)
    return result


def simulate(body, position, remaining):
    grows = position in remaining
    occupied = set(body if grows else list(body)[:-1])
    if position in occupied:
        return None
    new_body = deque([position])
    new_body.extend(body)
    if not grows:
        new_body.pop()
    return new_body


def natural_route(grid, seed):
    width = len(grid)
    foods = {(x, y) for x, week in enumerate(grid) for y, count in enumerate(week) if count}
    body = deque([(0, 0)])
    route = [(0, 0)]
    foods.discard((0, 0))
    randomizer = Random(seed)
    max_steps = width * 7 * 3

    for step in range(max_steps):
        if not foods:
            break
        ranked = []
        for next_pos in adjacent(body[0], width):
            if len(body) > 1 and next_pos == body[1]:
                continue  # never reverse into the neck
            updated = simulate(body, next_pos, foods)
            if updated is None:
                continue
            occupied = set(updated)
            occupied.discard(updated[-1])  # tail can move away next frame
            d = distances(next_pos, occupied, width)
            nearest = min((d.get(food, 100000) for food in foods if food != next_pos), default=0)
            if nearest == 100000:
                continue
            free_space = len(d)
            # Do not create sealed pockets before collecting the rest.
            if foods - {next_pos} and free_space < min(8, width * 7 - len(updated)):
                continue
            # Prefer food nearby; turn naturally when equally good, with
            # deterministic tie-breaking variations on each attempt.
            direction = ((next_pos[0] - body[0][0]), (next_pos[1] - body[0][1]))
            old_direction = ((body[0][0] - body[1][0]), (body[0][1] - body[1][1])) if len(body) > 1 else None
            score = (nearest, 0 if next_pos in foods else 1, -free_space,
                     0 if old_direction is not None and direction != old_direction else 1,
                     randomizer.random())
            ranked.append((score, next_pos, updated))
        if not ranked:
            return None
        _, chosen, body = min(ranked, key=lambda item: item[0])
        route.append(chosen)
        foods.discard(chosen)
    if foods:
        return None

    # Once all food is gone, intentionally collide with a non-neck body cell.
    # No 180-degree turn is allowed even for this final move.
    for _ in range(width * 7 * 5):
        head = body[0]
        neighbors = [p for p in adjacent(head, width) if len(body) < 2 or p != body[1]]
        for position in neighbors:
            if position in list(body)[:-1]:
                route.append(position)
                return route
        safe = []
        for position in neighbors:
            next_body = simulate(body, position, set())
            if next_body is not None:
                blocked = set(next_body)
                blocked.discard(next_body[-1])
                space = len(distances(position, blocked, width))
                crowd = min((abs(position[0]-part[0]) + abs(position[1]-part[1])
                             for part in list(next_body)[2:]), default=999)
                safe.append(((crowd, -space, randomizer.random()), position, next_body))
        if not safe:
            break
        _, position, body = min(safe, key=lambda item: item[0])
        route.append(position)
    return None


def fallback_route(grid):
    """A single non-overlapping, adjacent-cell sweep: no reverse and no early self-collision.

    Keep the top row until last. Cover columns left-to-right, then return on
    the top row; the extra right-side lane makes this possible for any width.
    """
    width = len(grid)
    route = [(0, 0)]
    route.extend((0, y) for y in range(1, 7))
    for x in range(1, width):
        if x % 2:
            route.append((x, 6))
            route.extend((x, y) for y in range(5, 0, -1))
        else:
            route.append((x, 1))
            route.extend((x, y) for y in range(2, 7))

    # At the final column, the endpoint is either the first or the last day.
    if route[-1][1] == 1:
        route.extend((width - 1, y) for y in range(0, 0, -1))  # no-op, documented
        route.append((width - 1, 0))
    else:
        route.append((width, 6))
        route.extend((width, y) for y in range(5, -1, -1))
        route.append((width - 1, 0))
    route.extend((x, 0) for x in range(width - 2, -1, -1))

    # All contributions are gone. Intentionally fold into our own body to die.
    # Inbound direction is left, so first turn down; never make a 180-degree turn.
    route.extend([(0, 1), (0, 2), (1, 2), (1, 1), (0, 1)])
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(route, route[1:]))
    assert all(
        (route[i][0] - route[i-1][0], route[i][1] - route[i-1][1])
        != (route[i-2][0] - route[i-1][0], route[i-2][1] - route[i-1][1])
        for i in range(2, len(route))
    )
    return route



def make_route(grid):
    # Never silently revert to the rigid column-by-column sweep.
    # Explore deterministic variations of the flexible food-seeking route.
    for seed in range(6):
        print(f'Trying safe route {seed + 1}/6', flush=True)
        candidate = natural_route(grid, seed)
        if candidate is not None:
            print(f"Using flexible nearest-food route (seed {seed})")
            return candidate
    raise RuntimeError(
        'No complete safe food-seeking route found within the bounded search. '
        'The previous SVG remains intact.'
    )


def svg(grid, route, dark):
    pitch, cell, padding = 13, 10, 17
    width = padding * 2 + len(grid) * pitch + cell
    height = padding * 2 + 6 * pitch + cell
    palette = (["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"] if dark
               else ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"])
    snake = "#65e6fc"
    food = {(x, y) for x, week in enumerate(grid) for y, count in enumerate(week) if count}
    eaten = {}
    growth = []
    count = 0
    for i, pos in enumerate(route):
        if pos in food and pos not in eaten:
            eaten[pos] = i
            count += 1
        growth.append(count)
    if len(eaten) != len(food):
        raise RuntimeError("The route failed to eat all contributions")

    # One SVG path is the entire snake's traveled trajectory. Its moving visible
    # dash is the body. The dash grows by exactly one cell per eaten square.
    # The planned route never repeats a cell before the deliberate final crash.
    def xy(p):
        return (padding + p[0] * pitch + cell / 2,
                padding + p[1] * pitch + cell / 2)
    points = [xy(p) for p in route]
    path = " ".join(("M" if i == 0 else "L") + f"{x:g},{y:g}" for i, (x, y) in enumerate(points))
    n = len(route)
    motion_steps = n - 1
    travel = motion_steps * 0.095
    duration = travel + 1.2
    key_times = [i * 0.095 / duration for i in range(n)] + [1.0]
    keys = ";".join(f"{t:.7f}" for t in key_times)
    dash_gap = (motion_steps + len(food) + 20) * pitch
    lengths = [pitch * (2 + g) for g in growth]
    offsets = [lengths[i] - pitch * i for i in range(n)]
    dashes = ";".join(f"{v:g} {dash_gap:g}" for v in lengths + [lengths[-1]])
    dash_offsets = ";".join(f"{v:g}" for v in offsets + [offsets[-1]])
    coord_x = ";".join(f"{p[0]:g}" for p in points + [points[-1]])
    coord_y = ";".join(f"{p[1]:g}" for p in points + [points[-1]])
    dur = f"{duration:.3f}s"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Classic snake eats GitHub contributions, grows, collides, then restarts">',
        '<title>GitHub contribution snake — classic game</title>',
    ]
    for x, week in enumerate(grid):
        for y, value in enumerate(week):
            level = 0 if value == 0 else 1 if value < 3 else 2 if value < 6 else 3 if value < 10 else 4
            px, py = padding + x * pitch, padding + y * pitch
            parts.append(f'<rect x="{px}" y="{py}" width="{cell}" height="{cell}" rx="2" fill="{palette[level]}">')
            if (x, y) in eaten:
                t = key_times[eaten[(x, y)]]
                # Keep food hidden after it has been eaten until the next full loop.
                parts.append(f'<animate attributeName="opacity" values="1;0;0" keyTimes="0;{max(0.000001, t):.7f};1" calcMode="discrete" dur="{dur}" repeatCount="indefinite"/>')
            parts.append('</rect>')
    parts += [
        f'<path d="{escape(path, quote=True)}" fill="none" stroke="{snake}" stroke-width="8.5" stroke-linejoin="round" stroke-linecap="round" stroke-dasharray="{lengths[0]} {dash_gap}" stroke-dashoffset="{offsets[0]}">',
        f'<animate attributeName="stroke-dasharray" values="{dashes}" keyTimes="{keys}" dur="{dur}" repeatCount="indefinite" calcMode="discrete"/>',
        f'<animate attributeName="stroke-dashoffset" values="{dash_offsets}" keyTimes="{keys}" dur="{dur}" repeatCount="indefinite" calcMode="linear"/>',
        '</path>',
        f'<circle r="4.6" fill="{snake}" cx="{points[0][0]}" cy="{points[0][1]}">',
        f'<animate attributeName="cx" values="{coord_x}" keyTimes="{keys}" dur="{dur}" repeatCount="indefinite" calcMode="linear"/>',
        f'<animate attributeName="cy" values="{coord_y}" keyTimes="{keys}" dur="{dur}" repeatCount="indefinite" calcMode="linear"/>',
        # The head flashes red at the intentional final collision.
        f'<animate attributeName="fill" values="{snake};{snake};#ff6b6b;#ff6b6b" keyTimes="0;{key_times[-2]:.7f};{min(1,key_times[-2]+0.00001):.7f};1" dur="{dur}" repeatCount="indefinite"/>',
        '</circle>', '</svg>',
    ]
    return "\n".join(parts) + "\n", len(eaten), len(route)


def main():
    grid = get_grid()
    route = make_route(grid)
    out = Path("dist")
    out.mkdir(exist_ok=True)
    for dark, filename in [(False, "github-snake.svg"), (True, "github-snake-dark.svg")]:
        result, food_count, steps = svg(grid, route, dark)
        (out / filename).write_text(result, encoding="utf-8")
    print(f"Classic Snake generated: {food_count} contributions eaten; {steps} positions; grows and crashes before looping.")

if __name__ == "__main__":
    main()
