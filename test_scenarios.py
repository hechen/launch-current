"""Deterministic behavior checks, not evidence of forecast accuracy."""
import copy
import json
import math
import sys
from datetime import timedelta
import main


def check(path):
    with open(path, encoding='utf-8') as handle:
        case = json.load(handle)
    start = main.timestamp(case['day_start'])
    reference = main.forecast(case)
    def samples(values):
        return [{'at': (start + timedelta(minutes=i)).isoformat(), 'viewers': value,
                 'channels': None} for i, value in values]
    cases = {
        'flat': [(i, 100) for i in range(60)],
        'rising': [(i, 50 + 2 * i) for i in range(60)],
        'falling': [(i, 170 - 2 * i) for i in range(60)],
        'sparse': [(i, 50 + 2 * i) for i in range(0, 60, 10)],
        'outliers': [(i, 1000000 if i in (1, 58) else 100) for i in range(60)],
    }
    signals = {name: main.minute_signal(samples(data), start) for name, data in cases.items()}
    assert signals['rising'] > 0 > signals['falling']
    assert signals['flat'] == signals['sparse'] == signals['outliers'] == 0
    assert all(abs(value) <= 0.15 * math.log(1.5) for value in signals.values())
    print('minute signals:', ' '.join(f'{name}={value:+.6f}' for name, value in signals.items()))
    for name, data in cases.items():
        test = copy.deepcopy(case)
        test['history'] = samples(data)
        result = main.forecast(test)
        a, b = reference['hours'][0]['q'][2], result['hours'][0]['q'][2]
        print(f'{name} hour-2 median multiplier: {b / a:.6f}')
        assert all(0 < q <= 1e9 for row in result['hours'] for q in row['q'])
    quiet = copy.deepcopy(case)
    quiet['known'] = [{'viewers': 0, 'channels': 0}]
    quiet['history_hourly'] = [{'from': (start - timedelta(hours=i)).isoformat(),
                                'viewers': 0, 'channels': 0} for i in range(1, 80)]
    quiet['history'] = []
    q = main.forecast(quiet)['hours'][0]['q']
    assert q[2] == 1 and q == sorted(q)
    print('zero viewers / no broadcasts q:', q)
    large = copy.deepcopy(case)
    large['known'] = [{'viewers': 400_000_000, 'channels': 1}]
    large['streams'] = [{'viewers': 400_000_000}]
    # With no analogues, the persistence distribution must not cap at first hour.
    large['comparables'] = []
    result = main.forecast(large)
    assert max(q for row in result['hours'] for q in row['q']) >= 400_000_000
    assert all(0 < q <= 1e9 for row in result['hours'] for q in row['q'])
    print('dominant-stream largest q:', max(q for row in result['hours'] for q in row['q']))
    missing = copy.deepcopy(quiet)
    missing['comparables'] = []
    assert len(main.forecast(missing)['hours']) == 23
    print('missing references: valid')


if __name__ == '__main__':
    check(sys.argv[1])
