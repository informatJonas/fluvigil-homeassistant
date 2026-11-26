# Changelog

All notable changes to this integration are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), the versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-11-26

### Added

- Icon of the integration, shipped with it and shown by Home Assistant 2026.3 and newer.
- Category and country information for the Home Assistant Marketplace.
- The repository is checked by hassfest and the HACS validation.

### Changed

- The installation guide covers the Marketplace of Home Assistant 2026.11 and HACS for older
  versions.

### Fixed

- The integration failed to load on installations without the `async_timeout` package,
  which Home Assistant no longer brings along by itself. It now uses the standard library.
- The description promised groundwater levels, reservoir storage and forecasts, which the
  integration does not offer, and called every value a height above the gauge datum.

## [0.2.0] - 2026-11-26

### Added

- Re-authentication: a rejected API key can be replaced in Home Assistant. One dialog updates
  every gauge that used the old key on the same server and closes the other requests. The
  sensors keep reporting while the request is open; a new key restores the limits of the tier.
- The source notice of each value is shown as the attribution of its sensor.
- A gauge Fluvigil has no value for is named as such in the setup dialog instead of being
  added.

### Changed

- A gauge that loses its value while running becomes unavailable, is logged once at warning
  level and recovers on its own. The integration stays loaded instead of retrying its setup.
- The same gauge is recognised in the setup dialog whether it is known by its older
  `<source>:<id>` or by its `fp_` id. Existing entries and entities keep their ids.

### Fixed

- A revoked API key went unnoticed: the value request treats it as no key at all. The key is
  now checked at start and once an hour, at the cost of one request per gauge and hour.
- A rate limit hit while searching for a gauge is reported as such.

## [0.1.1] - 2026-09-10

### Added

- MIT licence and a code owner in the manifest.

## [0.1.0] - 2026-09-09

- First release: one gauge, one water level sensor, setup in the user interface.
