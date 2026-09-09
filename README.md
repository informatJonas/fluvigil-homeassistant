# Fluvigil for Home Assistant

Brings German water levels into Home Assistant, so a rising gauge can switch on a pump,
close a valve or send a notification — not just show a number.

## Why this and not one of the existing integrations

Home Assistant already ships an integration for the federal waterways, and a community
integration covers the sixteen state flood portals. Both are good, and for those gauges you
may not need this one.

What this adds is what neither has: **groundwater levels, reservoir storage, Swiss gauges and
published forecasts**, all in one place and one shape. And it does not scrape sixteen portals
inside your installation — when a state portal changes its layout, that is fixed once on the
server, not in a release you have to wait for.

## Install

Add this repository as a **custom repository** in HACS (category: Integration), then install
it and restart Home Assistant:

```
HACS → ⋮ → Custom repositories
Repository: https://github.com/informatJonas/fluvigil-homeassistant
Category:   Integration
```

## Setup

1. Create an API key at https://fluvigil.de → Account → API keys. Any tier works.
2. In Home Assistant: **Settings → Devices & services → Add integration → Fluvigil**.
3. Paste the key. An invalid key is rejected right there, not hours later.
4. Search for a gauge by name or water body and pick one.

You get a **Water level** sensor in centimetres above the gauge datum, with the measurement
time, the water body and the flood classification as attributes.

## How it behaves when things go wrong

- **Service unreachable:** the sensor becomes *unavailable*. It does not keep showing the
  last reading as if it were current — an automation would act on that.
- **Key revoked or expired:** Home Assistant asks you to re-authenticate instead of the
  sensor quietly going flat.
- **Rate limit reached:** reported as such, so you know it is your tier's budget and not an
  outage.

## Update interval

15 minutes, on every tier. The upstream sources publish on a 15-minute raster, so polling
faster would fetch the same number twice.

## License

MIT.
