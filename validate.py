"""Leave one title out; supply the path to a public practice input."""
import json
import math
import sys
from datetime import timedelta
import main


def score(prediction, bins):
    losses, covered = [], []
    for row in prediction['hours']:
        y = bins.get(row['hour'] - 1)
        if y is None:
            continue
        q = row['q']
        d = [math.log(max(1, y)) - math.log(max(1, v)) for v in q]
        losses.extend(2 * max(t * x, (t - 1) * x) for t, x in zip(main.LEVELS, d))
        covered.append(q[0] <= max(1, y) <= q[-1])
    return sum(losses) / len(losses), sum(covered) / len(covered)


def main_validate(path):
    with open(path, encoding='utf-8') as f:
        case = json.load(f)
    games = main.library(case)
    # These console-local titles are never used in any fitted forecast.
    reserved = ('Ghost of Yōtei', 'The Legend of Zelda: Tears of the Kingdom', 'Ghost of Tsushima', 'Stellar Blade')
    results = []
    for name, kind, bins, _ in games:
        item = next(x for x in case['comparables'] if x['name'] == name)
        day = main.timestamp(item['day_start'])
        test = dict(case, day_start=item['day_start'], known=[{'viewers': bins[0]}],
                    history_hourly=[{'from': (day + timedelta(hours=h)).isoformat(), 'viewers': v}
                                    for h, v in bins.items() if h <= 0])
        vals = [score(main.forecast(test, excluded=reserved + (name,), mode=mode), bins)
                for mode in ('persistence', 'uniform', 'simple', 'model')]
        results.append((name, kind, vals))
        print(f'{name[:38]:38} {kind:7} ' + ' '.join(f'{x[0]:.3f}/{x[1]:.2f}' for x in vals))
    quiet_backtest(case)
    for label, group in [('all', results), ('development', [r for r in results if r[0] not in reserved]), ('reserved console-local (selected after initial inspection)', [r for r in results if r[0] in reserved])]:
        print(label, len(group), ' '.join(f'{sum(r[2][i][0] for r in group)/len(group):.4f}/{sum(r[2][i][1] for r in group)/len(group):.3f}' for i in range(4)))


def quiet_backtest(case):
    """Historical quiet windows overlap: this is diagnostic, not independent CV."""
    references = [x for x in case['comparables'] if 'target-history' in (x.get('unlock') or '').lower()]
    if not references:
        return
    item = references[0]
    bins = main.observations(item['hourly'], main.timestamp(item['day_start']))
    errors = [[], []]
    for h in sorted(bins):
        old = [v for k, v in bins.items() if h - 240 <= k < h - 24]
        future = [v for k, v in bins.items() if h < k <= h + 24]
        if len(old) < 12 or not future:
            continue
        baseline = main.median(old)
        if baseline <= 0 or bins[h] >= 1000 or bins[h] >= 3 * baseline:
            continue
        for y in future:
            for index, center in enumerate((max(1, bins[h]), max(1, (bins[h] + baseline) / 2))):
                errors[index].append(abs(math.log(max(1, y) / center)))
    if errors[0]:
        print('quiet overlapping pairs:', len(errors[0]), 'latest / baseline blend MALE:',
              *(round(sum(e) / len(e), 4) for e in errors))


if __name__ == '__main__':
    main_validate(sys.argv[1])
