# Troubleshooting

Start with the status in the upper-left corner. `Updated at ...` means the
complete Wi-Fi and Home Assistant cycle succeeded. `Update failed at ...` means
the displayed glucose content came from the last successful cache, while the
battery value was read during the failed attempt.

## The clock shows UTC or the wrong local time

The dedicated firmware defaults to Pacific time with
`PST8PDT,M3.2.0,M11.1.0`. For another location, rebuild with the appropriate
POSIX value in `SUGARTV_TZ`. Keep the full `PLATFORMIO_BUILD_FLAGS` value in the
same shell during both build and upload because PlatformIO may rebuild before
flashing.

If the displayed time is exactly seven hours ahead of Pacific daylight time,
the device is running an older build whose fallback was `UTC0`. Reapply the
current patch, rebuild, and flash it again.

## SugarTV cannot find the intended sensor

First verify the token and URL from the build instructions in the README. By
default, discovery chooses the first valid `sensor.*` state whose
`device_class` is `blood_glucose_concentration`.

An HTTP `401` from `/api/` or `/api/states` means the embedded Home Assistant
token is invalid or expired. Create a new long-lived access token, verify that
it returns `200` from `/api/`, and only then rebuild and flash the firmware.
Sensor discovery cannot recover from an authentication failure, even when the
glucose entity and its current state are otherwise valid.

To select a specific source, copy `firmware/sugartv.example.json` to
`/.crosspoint/sugartv.json` on the X3 SD card and set `glucose_value`. Set
`glucose_trend` only when the integration exposes trend as a separate entity;
otherwise SugarTV resolves common sibling entities and attributes itself.

## A saved Wi-Fi network is unavailable

Automatic wakes try only a bounded set of saved, visible networks and then
render a failed update. They do not keep scanning once per minute while the X3
remains awake.

Press the rightmost physical button labelled `Manage Wi-Fi` to open the manual
network list. Manual mode disables automatic reconnection to the current
network so another SSID can be selected. A short power-button press requests an
immediate normal update instead.

## Wi-Fi requires a captive-portal confirmation

SugarTV cannot complete a browser-based captive-portal login. Home Assistant
requests within one update share a 20-second HTTP budget, so a portal, stalled
response, or route without usable access should end in a failed-update frame
and return to the normal sleep cadence.

Use `Manage Wi-Fi` to select a network that can reach Home Assistant without an
interactive login. If a cycle remains awake indefinitely on the current patch,
collect the diagnostic event described below rather than repeatedly power
cycling the device.

## The X3 does not appear as a serial device

Confirm that the USB-C cable carries data, connect the X3 directly rather than
through an unpowered hub, and wake it before looking for the port. Typical port
names are `/dev/cu.usbmodem*` on macOS and `/dev/ttyACM*` on Linux.

For a stock or USB-locked unit, follow CrossPoint's pinned
[installation and unlocker notes](https://github.com/crosspoint-reader/crosspoint-reader/blob/e00f5958dfeea2a3e640c39eb78186fd20996f4b/README.md#install-firmware).

## Leave SugarTV or force an update

- Hold the power button to clear the scheduled-cycle markers and return to the
  normal CrossPoint interface.
- Briefly press the power button to update immediately.
- Press the rightmost button to manage Wi-Fi.

## Collect diagnostics safely

Each automatic cycle appends one JSON object to
`/.crosspoint/logs/sugartv-YYYY-MM-DD.jsonl` on the SD card. The event records
the result, failure stage, timing, wake cause, network state, battery, memory,
and system-log tail. It excludes the Home Assistant token, Wi-Fi password, and
response body.

The log still contains private operational details such as SSID, BSSID, local
addresses, and requested Home Assistant URLs. Redact those fields before
sharing a diagnostic file outside the trusted environment.
