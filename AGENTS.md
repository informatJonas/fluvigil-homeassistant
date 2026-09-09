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
- `GET /api/v1/stations/{id}/state` — 266 bytes: value, measurement time, severity, headline.

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
  rely on it (`tests/conftest.py` registers the package by hand so `__init__.py` never runs).
- **Tests run against a real aiohttp server**, not a mocking library: the client's whole job
  is reacting to what HTTP returns, and a stub that reimplements those semantics can agree
  with the client while both are wrong.
- Poll interval is 15 minutes and that is a measured ceiling, not a preference — the upstream
  sources publish on that raster, so a shorter interval fetches the same number twice.

## Testing

```bash
python3 -m venv .venv && .venv/bin/pip install aiohttp async_timeout pytest pytest-asyncio
.venv/bin/python -m pytest -q
```

The coordinator, config flow and sensor are deliberately uncovered: they are thin wrappers
over Home Assistant machinery, and testing them means installing the framework. Worth doing
when this is submitted upstream; not worth it for a first gauge.

## Not in scope yet

Multiple gauges per entry, discharge and groundwater sensors, alert rules from Fluvigil
(those belong in the user's own automations), and submission to Home Assistant core — the
community distribution comes first because it reaches users in days rather than months.
