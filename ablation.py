"""Pre-specified channel and distribution experiments; does not change main.py."""
import json
import math
import sys
from datetime import timedelta
import main
import validate

CACHE = {}


def channel_features(rows, start, first=None):
    channels = main.observations([{'from': r.get('from') or r.get('at'), 'viewers': r.get('channels')}
                                  for r in rows if r.get('channels') is not None], start)
    if first is not None:
        channels[0] = first
    if channels.get(0) is None:
        return None
    previous = [channels[h] for h in range(-6, 0) if h in channels]
    if len(previous) < 3:
        return None
    return channels[0], math.log((channels[0] + 1) / (main.median(previous) + 1))


def midpoint(values, level):
    values.sort()
    total = sum(w for _, w in values)
    points = []
    mass = 0.0
    for value, weight in values:
        points.append(((mass + weight / 2) / total, value))
        mass += weight
    if level <= points[0][0]:
        return points[0][1]
    for (a, x), (b, y) in zip(points, points[1:]):
        if level <= b:
            return x + (y - x) * (level - a) / (b - a)
    return points[-1][1]


def experiment(case, excluded, channels, smooth):
    start = main.timestamp(case['day_start'])
    hist = main.observations(case['history_hourly'], start)
    known = case['known'][0]
    first = max(1, known['viewers'])
    hist[0] = first
    target = main.features(hist)
    tc = channel_features(case['history_hourly'], start, known.get('channels'))
    output = []
    for h in range(1, 24):
        values = []
        for item in case['comparables']:
            if item['name'] in excluded or main.launch_kind(item) == 'exclude':
                continue
            key = item['name']
            if key not in CACHE:
                day = main.timestamp(item['day_start'])
                CACHE[key] = (main.observations(item['hourly'], day), channel_features(item['hourly'], day))
            bins, ac = CACHE[key]
            if 0 not in bins or bins[0] < 1 or h not in bins or sum(i in bins for i in range(1, 24)) < 18:
                continue
            f = main.features(bins)
            distance = ((f[0] - target[0]) / 2.5) ** 2 + ((f[1] - target[1]) / 1.8) ** 2
            w = math.exp(-0.5 * distance) * {'rolling': 2, 'console': 1.5, 'other': 0.6, 'global': 0.35}[main.launch_kind(item)]
            if channels and tc is not None and ac is not None:
                # A half-strength blend limits the influence of missing/noisy counts.
                density = math.log((first + 1) / (tc[0] + 1))
                other_density = math.log((bins[0] + 1) / (ac[0] + 1))
                d = ((density - other_density) / 2.0) ** 2 + ((tc[1] - ac[1]) / 1.5) ** 2
                w *= 0.5 + 0.5 * math.exp(-0.5 * d)
            ratio = math.log(max(1, bins[h]) / bins[0])
            if smooth:
                neighbors = [math.log(max(1, bins[k]) / bins[0]) for k in (h-1, h+1) if k in bins]
                if neighbors:
                    ratio = 0.8 * ratio + 0.2 * sum(neighbors) / len(neighbors)
            values.append((ratio, w))
        if not values:
            output.append({'hour': h + 1, 'q': [first] * 5})
            continue
        values.sort()
        if smooth:
            total = sum(w for _, w in values)
            ess = total * total / sum(w*w for _, w in values)
            center = midpoint(values, 0.5)
            # Weak, symmetric log-ratio prior, strongest below eight effective titles.
            prior = total * 0.1 * max(0, (8 - ess) / 8)
            if prior:
                values.extend([(center - 1.0, prior / 2), (center + 1.0, prior / 2)])
            qs = [first * math.exp(midpoint(values, q)) for q in main.LEVELS]
        else:
            total = sum(w for _, w in values)
            def wq(q):
                mass = 0
                for value, w in values:
                    mass += w
                    if mass >= total*q:
                        return value
                return values[-1][0]
            qs = [first * math.exp(wq(q)) for q in main.LEVELS]
        output.append({'hour': h+1, 'q': [round(min(1e9, max(1, q)), 4) for q in qs]})
    return {'hours': output}


def run(path):
    with open(path, encoding='utf-8') as handle:
        case = json.load(handle)
    items = case['comparables']
    reserved = ('Ghost of Yōtei', 'The Legend of Zelda: Tears of the Kingdom', 'Ghost of Tsushima', 'Stellar Blade')
    for evaluation in ('chronological', 'holdout'):
        results = []
        for item in items:
            kind = main.launch_kind(item)
            if 'target-history' in (item.get('unlock') or '').lower():
                continue
            if evaluation == 'holdout' and kind == 'exclude':
                continue
            day = main.timestamp(item['day_start'])
            bins = main.observations(item['hourly'], day)
            if 0 not in bins or bins[0] < 1 or any(h not in bins for h in range(1,24)):
                continue
            pool = [i for i in items if main.timestamp(i['day_start']) < day] if evaluation == 'chronological' else items
            excluded = (item['name'],) if evaluation == 'chronological' else reserved + (item['name'],)
            rows = [r for r in item['hourly'] if main.timestamp(r['from']) < day + timedelta(hours=1)]
            first_rows = [r for r in rows if day <= main.timestamp(r['from']) < day + timedelta(hours=1)]
            channel = first_rows[0].get('channels') if first_rows else None
            test = dict(case, game={'name': item['name']}, day_start=item['day_start'], comparables=pool,
                        known=[{'viewers':bins[0], 'channels':channel}], history_hourly=rows, history=[])
            if len(main.library(test, excluded)) < (8 if evaluation == 'chronological' else 1):
                continue
            predictions = [main.forecast(test, excluded), experiment(test, excluded, True, False),
                           experiment(test, excluded, False, True), experiment(test, excluded, True, True)]
            reference = experiment(test, excluded, False, False)
            assert reference == predictions[0], 'experimental control differs from the current model'
            scores = [validate.score(p, bins) for p in predictions]
            console = kind in ('rolling', 'console') and 'pc' not in (item.get('platforms') or '').lower()
            results.append((item['name'], console, item['name'] in reserved, scores))
        groups = [('all', results), ('console', [r for r in results if r[1]])]
        if evaluation == 'holdout':
            groups.append(('reserved', [r for r in results if r[2]]))
        for label, group in groups:
            print(evaluation, label, 'n=',len(group))
            for j, name in enumerate(('current', 'channels', 'smoothing', 'both')):
                print(' ', name, 'loss', f'{sum(r[3][j][0] for r in group)/len(group):.6f}',
                      'coverage', f'{sum(r[3][j][1] for r in group)/len(group):.4f}')
        for name, console, reserved_title, scores in results:
            if console or reserved_title:
                print(' ',name, *(f'{s[0]:.5f}' for s in scores))


if __name__ == '__main__':
    run(sys.argv[1])
