# Home Assistant integration engineering review

Reviewed against the [integration concepts](https://contributors.home-assistant.io/core/integrations/concepts/) and [quality-scale guidance](https://contributors.home-assistant.io/core/quality-scale/rules/) on 2026-10-30. This is a custom integration self-review, not an official Home Assistant quality-tier certification.

## Applied conventions

- Protocol encoding, authentication, network I/O, camera setters and response parsing remain in the separate Python library. The Home Assistant adapter handles lifecycle and entity mapping. No vendor JavaScript executes in the integration.
- One local camera is one config entry and one device. A typed `ConfigEntry[MipcCoordinator]` keeps the coordinator in `entry.runtime_data`. Unique IDs derive from the device serial and stable setting/microphone tokens, never the IP address or display name.
- Setup authenticates and fetches initial data before creating entities. It verifies the saved device identity, closes resources on setup failure or cancellation, and distinguishes retryable connectivity failures from invalid credentials and a different device.
- Config flows validate before creating an entry and reject duplicates. Reauth and reconfigure update the same entry and reject another serial. Options reload the integration. Connection secrets are not copied into options.
- All blocking library calls execute in Home Assistant's executor. A hub lock serializes device requests; a coordinator lock keeps each write and its read-back together across setting platforms. Platform request limits are explicit: 1 for action/media platforms, 0 for coordinator-only read platforms.
- A shared coordinator polls every 60 seconds and uses native authentication/update exceptions for reauth, availability, retry and one-time failure/recovery logs. The last-seen timestamp can change each successful poll, so suppressing all unchanged-state notifications is not appropriate for that diagnostic.
- Settings appear only for observed fields and supported types. Lost optional readings become unavailable. Read-only helpers never send maintenance writes. An empty SD slot never becomes a usage percentage. The percentage sensor uses measurement state class; last-seen uses timestamp device class and connection uses connectivity device class.
- Entity names and select-mode labels live in translation resources. Icons live in `icons.json`. Exceptions are translated and include only sanitized exception class names. The movement action's configuration-entry selector is a camera picker rather than an unexplained raw-ID input.
- `has_entity_name`, stable unique IDs, device metadata and configuration/diagnostic categories are provided. Redundant firmware and last-seen sensors are disabled by default. The main camera has no redundant name suffix.
- Motor support is explicitly opted in; a readable document alone is not proof of a working action. Destructive maintenance and speculative motion-event sensors are not exposed. Hardware and firmware limits are documented.
- Diagnostics use an explicit whitelist, excluding credentials, host, device identifiers, raw documents and media URLs. SDK HTTP errors are sanitized. No HTTP control endpoint, access token, telemetry or background monitoring is added.
- Tests exercise successful and failed setup, cleanup, all configuration-flow paths, options reload, capability routing, immediate read-back, failures, recovery, media and movement actions. CI enforces 95% combined statement/branch coverage for integration code, plus Ruff, hassfest and HACS validation. The SDK has its own independent tests.
- The official MIPC logo ships locally under `brand/` as 256 and 512 pixel PNGs, with source/trademark attribution. It is not a Home Assistant logo or a generated approximation.

## Deliberate limits and remaining release work

The user requested a temporary SDK bundle for live testing. Core integrations normally use a separately published PyPI dependency; this beta vendors the exact reviewed library source, retains its BSD license and records its commit. The resource lookup is the only namespace adaptation. Before a normal dependency-based release, publish the updated SDK, replace the vendor adapter import with that pinned dependency, remove `_vendor`, and rerun offline and hardware tests. Do not silently fall back to the older PyPI release.

The SDK is synchronous and owns its serialized, bounded HTTP session. It runs in the executor rather than blocking the event loop. A native async SDK and injected web session would be a separate library change; no Platinum claim is made. Typed Home Assistant entry points do not imply that all dynamic camera response documents have a strict schema.

No reliable discovery metadata or actual motion-event delivery has been demonstrated, so automatic discovery and event entities are not claimed. Runtime capability changes are rediscovered on reload. Firmware updates, card formatting, reset and credential/network changes remain outside the integration's exposed actions. Home Assistant's existing error/reauth mechanisms cover current user-actionable failures; there are no speculative custom repair issues.

Only an f300 with firmware `v5.1.10.1811061306` has been hardware-tested. Both motors, JPEG snapshots, local RTMP consumption, Home Assistant HLS decoding and the exposed settings write paths were verified; broad firmware support, two-way talk, actual motion events and recording to an absent SD card are not promised.
