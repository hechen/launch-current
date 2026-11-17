# launch-current

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/hechen/launch-current/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/hechen/launch-current/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

LaunchCurrent forecasts five hourly Twitch audience quantiles using historical game launches.

## Run it

```sh
MAKEFUN_INPUT_DIR=/path/to/kit/input MAKEFUN_OUTPUT_DIR=/tmp/launch-current-out python3 main.py
```

## Reproduce the historical checks

Unpack the public competition kit and set `CASE` to its `input/p00.in` file. These checks forecast past releases from the supplied launch histories. The final target is a future day with 23 scored hours.

```sh
python3 validate.py "$CASE"
python3 test_scenarios.py "$CASE"
```

Historical viewer and channel counts are provided in the kit and attributed there to SullyGnome.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
