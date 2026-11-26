# Fluvigil — Home Assistant integration

A custom Home Assistant integration that brings German water levels from the Fluvigil
service into a local installation, so a gauge crossing a threshold can drive an actual
action — a pump, a valve, a notification — rather than only a message.

Workstation rules apply on top: `~/.claude/CLAUDE.md` + `~/.claude/rules/*`.

## Role

Advisor for a small, single-purpose integration whose users are technical and whose
failures are silent by nature. The lens that matters most here: **a sensor that stops being
true must stop reporting.** A stale reading presented as current is worse than no reading,
because an automation acts on it.

## The service it talks to

Fluvigil (`/opt/vibe-projects/homelab/pegel-monitor`, https://fluvigil.de) merges ten public
sources into one dataset. Two endpoints matter here:

- `GET /api/v1/me` — confirms an API key, returns tier and limits. The **only** route that
  rejects a bad key; everywhere else an unknown key is ignored and the request proceeds
  anonymously on free-tier limits, which is exactly how a typo becomes invisible.
- `GET /api/v1/stations/{id}/state` — compact: value, measurement time, severity, headline.
  `404` means the service delivers nothing for this gauge. It never answers `401` for a revoked
  key, which is why the coordinator asks `/me` as well (at start, then hourly). A rejected key
  starts re-authentication and the values keep running: they stay true without a key.
  `sourceNotice` is a licence condition and has to reach the user with the value (the sensor's
  attribution); a `full-only` notice is never shortened.

Answer shapes of the running and the next service generation are kept in `tests/fixtures`.

Decisions that constrain this integration — differentiation, station allowance per tier,
poll interval and why it is not a tiering dimension — are recorded in the service repository
under `docs/home-assistant-integration-decisions.md`. Read it before changing the interval
or the limits; the numbers there are argued, not assumed.

## Conventions

- **Python, Home Assistant conventions**, not this workstation's TypeScript ones. Async
  throughout, `DataUpdateCoordinator`, `ConfigFlow`, entity descriptions, translation keys.
- **One coordinator per config entry**, never one fetch per entity — request cost must not
  grow with the number of gauges a user adds.
- **`api.py` and `const.py` import nothing from Home Assistant.** That separation is what
  makes the network-facing half testable without installing the framework, and the tests
  rely on it (`tests/client/test_api.py` registers the package by hand so `__init__.py`
  never runs).
- **No third-party import without a `requirements` entry in the manifest.** A package that
  happens to be installed beside Home Assistant may be missing on the next installation.
- **Tests run against a real aiohttp server**, not a mocking library: the client's whole job
  is reacting to what HTTP returns, and a stub that reimplements those semantics can agree
  with the client while both are wrong.
- Poll interval is 15 minutes and that is a measured ceiling, not a preference — the upstream
  sources publish on that raster, so a shorter interval fetches the same number twice.

## Testing

```bash
python3 -m venv .venv
.venv/bin/pip install pytest-homeassistant==2026.11.3
./run-tests.sh
```

The release of `pytest-homeassistant` is the Home Assistant version it tests against; upgrade
them together. It is the package Home Assistant publishes itself and exists from 2026.11 on.

**Two runs, and that is not an accident.** The Home Assistant test plugin blocks sockets and
enforces its own cleanup across everything in its process, while `tests/client` exists
precisely to talk to a real local HTTP server. So the client half runs with plugin
autoloading off (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, only `pytest_asyncio.plugin` enabled)
and the Home Assistant half runs normally. Merging them into one command means giving up one
of the two, and both earn their keep:

- `tests/client` — the client against a real aiohttp server: status codes, malformed bodies,
  a connection that fails. A mock that reimplements HTTP semantics can agree with the client
  while both are wrong.
- `tests/homeassistant` — the config flow and the entity inside a real Home Assistant
  instance. This is where the acceptance criteria live: a bad key refused in the dialog, a
  sensor that afterwards carries value, unit and measurement time.

The Home Assistant half copies the integration into the test instance's config directory,
because discovery reads that directory and not the project.

## Not in scope yet

Multiple gauges per entry, discharge and groundwater sensors, alert rules from Fluvigil
(those belong in the user's own automations), and submission to Home Assistant core — the
community distribution comes first because it reaches users in days rather than months.
