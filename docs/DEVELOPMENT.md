# Development

[Back to the README](../README.md)

```sh
pip install -r requirements_test.txt
pytest -q --cov=custom_components.mipc_camera --cov-report=term-missing
ruff check .
ruff format --check .
```

Tests use synthetic camera data, block network access and cover initial setup, duplicate entries, failed and cancelled setup, reauthentication, reconfiguration, options reload, entity discovery, verified writes, unavailable/recovery transitions, optional capabilities, PTZ, camera media, unload and diagnostics. CI enforces at least 95% coverage of the integration, including branches; the bundled library is excluded because it has its own test suite. Live acceptance tests are separate and must use local private credentials; never commit credentials or camera images.

## Temporary library bundle

This beta includes the updated [Python library fork](https://github.com/brylee123/mipc-camera-client-python) inside `_vendor/mipc_camera_client`, version `0.2.0.dev0`, commit `b5428ebf5900dfcbc61ce04f5293e459910b3098`. **It does not install the older PyPI release.** The only adaptation is the resource package lookup in `catalog.py` so the RPC catalogue resolves inside the integration namespace. The original BSD license is retained in `_vendor/LICENSE`. This bundle can be replaced with a pinned published dependency when the updated library is released.

## Engineering guidance

See the [integration review](QUALITY.md) for lifecycle, capability detection, testing and packaging decisions. This is a community custom integration; no official Home Assistant quality tier is claimed.
