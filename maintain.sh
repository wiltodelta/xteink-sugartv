#!/usr/bin/env bash

set -euo pipefail

uv sync
uvx uv-outdated
uvx uv-secure uv.lock
uv run ruff check --fix .
uv run ruff format .
uv run pyright
uv run pytest -n auto
