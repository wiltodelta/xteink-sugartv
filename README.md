# Xteink SugarTV

Xteink SugarTV turns a dedicated Xteink X3 into a direct Home Assistant
glucose display. The device runs a patched CrossPoint build, reads Home
Assistant state and history itself, renders a native 528×792 portrait frame,
and wakes once per minute. No laptop, display server, or Lovelace card is
required at runtime.

While the SugarTV cycle is active, a short power-button press wakes the X3 and
requests an immediate update instead of waiting for the next timer wake. Holding
the power button exits the cycle and returns to the normal CrossPoint UI.

The screen follows the behavior of `homeassistant-sugartv-card`: source and
trend resolution for common glucose integrations, measurement timestamps,
history-derived delta and cadence, prediction text, threshold states, relative
time, missing data, and cadence-based aging. Color semantics are translated to
the one-bit panel: low and high readings gain an outline, urgent readings invert
the frame, and stale readings use ordered ink density. The upper-right value is
the battery percentage measured by the X3. The upper-left status always shows
the result and local time of the latest update attempt: `Updated at Aug 9, 3:55 PM`
after success or `Update failed at Aug 9, 3:56 PM` after failure. If Wi-Fi, Home
Assistant, or the configured glucose sensor is unavailable, the last successful
reading remains visible without changing its value, trend, delta, displayed
age, or battery percentage.

This is an informational display, not a medical device or a source for
treatment decisions.

The project is released under the MIT License. CrossPoint and icon attribution
are recorded in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Build the CrossPoint firmware

The patch is pinned to CrossPoint commit
`e00f5958dfeea2a3e640c39eb78186fd20996f4b` on the `develop` branch.

```bash
git clone https://github.com/crosspoint-reader/crosspoint-reader.git
cd crosspoint-reader
git checkout e00f5958dfeea2a3e640c39eb78186fd20996f4b
git apply /path/to/xteink-sugartv/firmware/patches/crosspoint-sugartv.patch
```

Supply the Home Assistant address, long-lived access token, and POSIX timezone
only through build flags. They must never be added to the patch or committed:

```bash
export HA_TOKEN='replace-with-token'
export PLATFORMIO_BUILD_FLAGS="-DSUGARTV_HA_URL=\\\"http://homeassistant.local:8123\\\" -DSUGARTV_HA_TOKEN=\\\"${HA_TOKEN}\\\" -DSUGARTV_TZ=\\\"PST8PDT,M3.2.0,M11.1.0\\\""
platformio run -e default
```

The result is `.pio/build/default/firmware.bin`. Building does not alter the X3;
flashing is a separate, explicit step after local validation.

The token is embedded in the resulting private binary because the device talks
to Home Assistant directly. With an `http://` URL, every API request sends that
token without transport encryption. Use HTTP only on a network whose risk you
accept; HTTPS is the appropriate production direction once certificate
validation is defined.

## Source and settings

Without settings, the firmware scans `/api/states` and selects the first valid
sensor whose Home Assistant `device_class` is
`blood_glucose_concentration`. The selected entity is cached, and a failed
entity request causes rediscovery. A temporarily `unknown` or `unavailable`
reading does not discard the cached source.

The latest successful reading is cached in
`/.crosspoint/sugartv-reading.json`. A successful cycle shows its absolute local
update time in the upper-left status. A failed automatic cycle renders the
cached reading exactly as it appeared on the last successful cycle, replaces
that status with `Update failed` and the failed attempt time on the same line,
then retries on the next one-minute wake. If no successful reading has been
cached, the main value is `N/A`.

Every automatic cycle appends a diagnostic JSON object to the daily SD-card log
at `/.crosspoint/logs/sugartv-YYYY-MM-DD.jsonl`. It retains 30 days of cycle,
reading, network, system, and error context without tokens, Wi-Fi passwords, or
response payloads. See [Architecture](docs/architecture.md) for the complete
logging contract.

On a cold wake, SugarTV first tries the last successful saved Wi-Fi network. If
the radio rejects that early attempt, a fresh scan tries visible saved networks
and permits one scan-confirmed retry of the original network. The attempt set
remains bounded, so an unavailable network cannot trap the device awake. A
manually selected open network is saved automatically with an empty password so
later headless wakes can reconnect to it.

The saved-network store is loaded immediately after SD-card initialization, so
the device UI and API do not temporarily report an empty list before the first
Wi-Fi activity opens it.

An optional `/.crosspoint/sugartv.json` file overrides discovery and display
defaults. The shared fields use the same names as `homeassistant-sugartv-card`:

```json
{
  "glucose_value": "sensor.jane_glucose_value",
  "glucose_trend": "sensor.jane_glucose_trend",
  "timestamp_attribute": "measurement_timestamp",
  "show_prediction": true,
  "relative_time": true,
  "dim_by_age": false,
  "show_age_states": false,
  "color_thresholds": false,
  "decimal_comma": false,
  "thresholds": {
    "urgent_low": 54,
    "low": 70,
    "high": 180,
    "urgent_high": 250
  }
}
```

`glucose_value`, `glucose_trend`, `timestamp_attribute`, `show_prediction`,
`relative_time`, `dim_by_age`, `color_thresholds`, and `thresholds` have the
card's meanings. Unlike the Lovelace card, `glucose_value` is optional because
the dedicated device can discover the first blood-glucose sensor itself.
Individual threshold values are optional and are merged with the defaults for
the sensor unit. A completed set that is not strictly ascending falls back to
the unit defaults, as does a complete set containing the other unit's defaults.

`show_age_states` and `decimal_comma` are X3-only parameters. The former gates
all age-based dithering while preserving the textual reading age; the latter
uses a comma as the mmol/L decimal separator. The ready-to-copy example is
[`firmware/sugartv.example.json`](firmware/sugartv.example.json).

## Local validation

Run these commands from the patched CrossPoint checkout:

```bash
c++ -std=c++17 -Isrc tools/test_sugartv_logic.cpp \
  src/activities/network/SugarTvLogic.cpp -o /tmp/test_sugartv_logic
/tmp/test_sugartv_logic
python3 tools/test_sugartv_preview.py
python3 tools/render_sugartv_preview.py \
  --font lib/EpdFont/builtinFonts/source/NotoSans/NotoSans-Regular.ttf \
  --output /tmp/sugartv-feature-matrix.png --matrix
```

The C++ test exercises the same timestamp, trend, sibling-entity, cadence,
aging, event-result, filename, and retention code compiled into the firmware.
The preview is not a second Python
implementation: it compiles and executes the same C++ frame renderer, bitmap
fonts, layout, and icon assets as the X3. Its tests reject clipped pixels, lock
the default framebuffer with a golden digest, and cover prediction placement,
threshold states, age density, missing history, unknown trend, the single-line
update status, and the complete visual matrix. The final command above writes that
matrix to `/tmp` for local inspection without adding generated device data to
the repository.

The sleep lifecycle requires a hardware soak test after flashing. Observe at
least 15 consecutive one-minute updates with the X3 disconnected from USB, then
repeat with USB connected. Both runs must retain timer wake and power-button
wake, advance the displayed measurement, and avoid hanging on entry to deep
sleep. A single successful wake is not sufficient validation.

## Reference server

The Python application under `src/xteink_sugartv` is retained as a local reference
renderer and a compatibility harness for the earlier `x3-trmnl` prototype. It
is not part of the direct-device runtime. It starts in synthetic-data mode with
the defaults from `.env.example`:

```bash
uv sync
uv run uvicorn xteink_sugartv.app:app --host 0.0.0.0 --port 8000
```

Copy `.env.example` to `.env`, customize it, and add `--env-file .env` to the
command when Home Assistant-backed rendering is needed. Run the complete local
quality gate with `./maintain.sh`.
