"""Data-only catalog of observed client calls; not a capability claim."""

import json
from importlib.resources import files

ENDPOINTS: dict[str, dict] = json.loads(
    files(__package__).joinpath("endpoints.json").read_text(encoding="utf-8")
)
