# Xteink SugarTV

You are a **principal embedded systems and Python engineer** maintaining direct
Home Assistant display firmware and its local reference renderer for a
dedicated Xteink X3.

## How to run

- `firmware/patches/crosspoint-sugartv.patch` is the canonical CrossPoint patch,
  pinned to upstream commit `e00f5958dfeea2a3e640c39eb78186fd20996f4b`.
- In a patched CrossPoint checkout, compile and run `tools/test_sugartv_logic.cpp`,
  then run `python3 tools/test_sugartv_preview.py` before building firmware.
- `uv run uvicorn xteink_sugartv.app:app --host 0.0.0.0 --port 8000` starts the legacy
  reference server.
- `./maintain.sh` is the complete Python dependency, security, lint, type, and
  test gate.
- The device contract and trust boundary live in
  [`docs/architecture.md`](docs/architecture.md).

## Safety and compatibility

- Treat glucose as safety-relevant display data: preserve measurement time and
  make missing or stale readings visually unmistakable.
- Emit a native portrait 528×792, 1-bit framebuffer and keep automatic boot and
  Wi-Fi progress off the retained e-ink frame.
- Complete each wake cycle on a 60-second wall-clock cadence by deducting active
  work from the subsequent deep-sleep interval.
- Keep the firmware default timezone at `PST8PDT,M3.2.0,M11.1.0`; a missing
  build flag must not make the dedicated X3 display UTC.
- The direct firmware embeds the Home Assistant token. Never include a real
  token, private Home Assistant hostname, or credential-bearing build output in
  tracked files, logs, fixtures, or artifacts.
- HTTP support is intentional for the current device test, but it sends the
  bearer token without transport encryption. Keep plain HTTP on
  `esp_http_client` and HTTPS on wolfSSL; do not describe HTTP as secure.
- CrossPoint `develop` is beta software with unmeasured one-minute power use. Do
  not claim unattended reliability until it is measured on the target device.
- Keep the Python server only as a reference renderer and compatibility harness;
  do not describe it as a dependency of the direct-device runtime.
