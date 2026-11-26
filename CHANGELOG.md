# Changelog

All notable changes to this integration are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), the versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0]

### Added

- Re-authentication: a rejected API key can be replaced in Home Assistant. One dialog updates
  every gauge that used the old key on the same server and closes the other requests.
- A gauge Fluvigil has no value for is named as such in the setup dialog instead of being
  added.

### Changed

- A gauge that loses its value while running becomes unavailable, is logged once at warning
  level and recovers on its own. The integration stays loaded instead of retrying its setup.
- The same gauge is recognised in the setup dialog whether it is known by its older
  `<source>:<id>` or by its `fp_` id. Existing entries and entities keep their ids.

### Fixed

- A revoked API key went unnoticed: the value request treats it as no key at all. The key is
  now checked at start and once an hour.
- A rate limit hit while searching for a gauge is reported as such.

## [0.1.1] - 2026-09-10

### Added

- MIT licence and a code owner in the manifest.

## [0.1.0] - 2026-09-09

- First release: one gauge, one water level sensor, setup in the user interface.
