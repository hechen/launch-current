"""Offline probabilistic forecasts from the case's own historical launches."""
import glob
import json
import math
import os
from datetime import datetime

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def median(values):
    values = sorted(values)
    n = len(values)
    return (values[(n - 1) // 2] + values[n // 2]) / 2 if n else 0.0



def observations(rows, start):
    """Use hourly bins only; multiple minute reads must not overweight an hour."""
    bins = {}
    for row in rows or []:
        value = row.get('viewers')
        if value is None or value < 0:
            continue
        try:
            h = int((timestamp(row.get('from') or row['at']) - start).total_seconds() // 3600)
        except (KeyError, ValueError, TypeError):
            continue
        bins.setdefault(h, []).append(value)
    return {h: sum(v) / len(v) for h, v in bins.items()}


def features(bins):
    first = max(1.0, bins.get(0, 1.0))
    recent = [bins[h] for h in range(-6, 0) if h in bins]
    recent_level = median(recent) if recent else first
    return math.log(first), math.log((first + 1) / (recent_level + 1))


def minute_signal(rows, start):
    """A weak, bounded adjustment, only when the hour has broad minute coverage."""
    reads = {}
    for row in rows or []:
        value = row.get('viewers')
        if value is None or value < 0 or not row.get('at'):
            continue
        try:
            minute = int((timestamp(row['at']) - start).total_seconds() // 60)
        except (TypeError, ValueError):
            continue
        if 0 <= minute < 60:
            reads[minute] = value
    if len(reads) < 12 or max(reads) - min(reads) < 40:
        return 0.0
    early = [v for minute, v in reads.items() if minute < 20]
    late = [v for minute, v in reads.items() if minute >= 40]
    if len(early) < 4 or len(late) < 4:
        return 0.0
    change = math.log((median(late) + 1) / (median(early) + 1))
    change = max(-math.log(1.5), min(math.log(1.5), change))
    return 0.15 * min(1.0, len(reads) / 60) * change


def launch_kind(item):
    unlock = (item.get('unlock') or '').lower()
    platforms = (item.get('platforms') or '').lower()
    if 'target-history' in unlock or 'not a launch' in unlock:
        return 'exclude'
    if 'early-access-contaminated' in unlock or 'tier: weak' in unlock:
        return 'exclude'
    if ('midnight local' in unlock or 'rolling' in unlock) and 'pc' not in platforms:
        return 'rolling'
    if 'simultaneous' in unlock or 'global unlock' in unlock or 'pc only' in platforms:
        return 'global'
    if 'midnight local' in unlock or 'rolling' in unlock:
        return 'rolling'
    if 'pc' not in platforms and any(x in platforms for x in ('ps4', 'ps5', 'switch', 'playstation')):
        return 'console'
    return 'other'


def library(case, excluded=()):
    result = []
    for item in case.get('comparables', []):
        if item.get('name') in excluded or launch_kind(item) == 'exclude':
            continue
        try:
            bins = observations(item.get('hourly'), timestamp(item['day_start']))
        except (KeyError, ValueError):
            continue
        if 0 not in bins or bins[0] < 1 or sum(h in bins for h in range(1, 24)) < 18:
            continue
        result.append((item['name'], launch_kind(item), bins, features(bins)))
    return result


def forecast(case, excluded=(), mode='model'):
    start = timestamp(case['day_start'])
    history = observations(case.get('history_hourly') or case.get('history'), start)
    known = (case.get('known') or [{}])[0].get('viewers')
    if known is None:
        known = history.get(0, 0)
    history[0] = max(0, known)
    first = max(1.0, known)
    target = features(history)
    refs = library(case, excluded)
    # A quiet, long-lived category is a different regime from a launch surge.
    older = [v for h, v in history.items() if -168 <= h < -24]
    # The target-history reference can extend a short live recorder history.
    for item in case.get('comparables', []):
        if 'target-history' in (item.get('unlock') or '').lower() and case.get('game', {}).get('name', '').lower() in item.get('name', '').lower():
            older.extend(v for h, v in observations(item.get('hourly'), start).items() if h < -24)
    long_history = len(older) >= 24
    baseline = median(older)
    channels = (case.get('known') or [{}])[0].get('channels')
    # Zero-valued histories still describe a quiet category; channels may be null.
    quiet = (long_history and first < 1000 and known <= max(3, 3 * baseline)
             and (channels is None or channels < 20 or baseline > 1))
    trend = minute_signal(case.get('history'), start)
    output = []
    for hour in range(2, 25):
        h = hour - 1
        if mode == 'persistence' or not refs:
            z = (-1.645, -0.674, 0, 0.674, 1.645)
            qs = [round(first * math.exp(x * 0.15 * math.sqrt(h)), 2) for x in z]
        else:
            weighted = []
            for name, kind, bins, f in refs:
                if h not in bins:
                    continue
                ratio = math.log(max(1, bins[h]) / max(1, bins[0]))
                if mode == 'uniform':
                    weight = 1.0
                elif mode == 'simple':
                    weight = {'rolling': 2.0, 'console': 1.5, 'other': 0.6, 'global': 0.35}[kind]
                else:
                    # Smooth weights avoid pretending a handful of close games are identical.
                    distance = ((f[0] - target[0]) / 2.5) ** 2
                    distance += ((f[1] - target[1]) / 1.8) ** 2
                    weight = math.exp(-0.5 * distance)
                    weight *= {'rolling': 2.0, 'console': 1.5, 'other': 0.6, 'global': 0.35}[kind]
                weighted.append((ratio, weight))
            if not weighted:
                qs = [first] * 5
            else:
                weighted.sort()
                total = sum(w for _, w in weighted)
                def wq(level):
                    acc = 0
                    for value, weight in weighted:
                        acc += weight
                        if acc >= total * level:
                            return value
                    return weighted[-1][0]
                qs = [first * math.exp(wq(q)) for q in LEVELS]
                if quiet:
                    # Quiet-history backtests favor the latest level over long-run shrinkage.
                    center = first
                    qs = [center * math.exp(z * 0.45) for z in (-1.645, -0.674, 0, 0.674, 1.645)]
        # Minute trends have no role in hourly-only practice cases. Their influence
        # fades as the horizon grows and is disabled in the no-lift regime.
        adjustment = math.exp(trend / math.sqrt(h)) if mode == 'model' and not quiet else 1.0
        output.append({'hour': hour, 'q': [round(min(1e9, max(1, q * adjustment)), 4) for q in qs]})
    return {'hours': output}


def main():
    source = os.environ.get('MAKEFUN_INPUT_DIR', '/input')
    destination = os.environ.get('MAKEFUN_OUTPUT_DIR', '/output')
    os.makedirs(destination, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(source, '*.in'))):
        with open(path, encoding='utf-8') as handle:
            case = json.load(handle)
        result = forecast(case)
        name = os.path.splitext(os.path.basename(path))[0] + '.out'
        with open(os.path.join(destination, name), 'w', encoding='utf-8') as handle:
            json.dump(result, handle, separators=(',', ':'), allow_nan=False)


if __name__ == '__main__':
    main()
