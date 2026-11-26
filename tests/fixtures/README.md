# Answer shapes

Two generations of the Fluvigil API answer this integration.

- `old_app/`: captured from https://fluvigil.de on 26 November 2026. `state_cologne.json` is the full answer,
  `search_cologne.json` keeps a subset of the keys of one list item. Gauges of Mecklenburg-Western Pomerania answer
  `404` there. `me_rejected.json` is the answer to a made-up key.
- `new_app/`: the next version of the service. Written to its shape, not captured: gauges
  have a public id (`fp_` and ten Crockford Base32 characters), the stored `<source>:<id>` stays a permanent alias in
  requests, the state answer names the gauge by the public id, the list adds `legacyId` during a transition, and
  gauges of Mecklenburg-Western Pomerania deliver a value. Ids, names and values of the MV gauge are invented.
- `contract/`: two examples from the published API contract, for the source notice: a gauge with two sources, and a
  provider whose notice must never be shortened (`form: full-only`).

Neither generation answers `401` on `/state` for a revoked key: the request is served as anonymous. Only `/me` rejects it.
