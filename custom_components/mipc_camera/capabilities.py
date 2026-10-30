"""Entity definitions are gated by observed, correctly typed fields."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Setting:
    key: str
    name: str
    platform: str
    path: tuple[str, ...]
    minimum: int = 0
    maximum: int = 100
    options: tuple[str, ...] = ()


SETTINGS = (
    *(
        Setting(field, name, "number", ("imaging", field))
        for field, name in (
            ("brightness", "Brightness"),
            ("contrast", "Contrast"),
            ("color_saturation", "Saturation"),
            ("sharpness", "Sharpness"),
        )
    ),
    Setting("speaker_volume", "Speaker volume", "number", ("speaker", "level")),
    Setting(
        "motion_sensitivity", "Motion sensitivity", "number", ("alerts", "motion_level")
    ),
    Setting(
        "night_motion_sensitivity",
        "Night motion sensitivity",
        "number",
        ("alerts", "motion_level_night"),
    ),
    Setting("flip", "Flip image", "switch", ("misc", "flip")),
    Setting("osd_text_enabled", "OSD text", "switch", ("osd", "text_enable")),
    Setting("osd_date", "OSD date", "switch", ("osd", "date", "date_enable")),
    Setting("osd_time", "OSD time", "switch", ("osd", "date", "time_enable")),
    Setting("recording", "Recording", "switch", ("recording", "task", "sch", "enable")),
    Setting(
        "day_night",
        "Day/night mode",
        "select",
        ("imaging", "mode"),
        options=("auto", "day", "night"),
    ),
    Setting("osd_text", "OSD text content", "text", ("osd", "text")),
)


def value_at(data, path):
    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            matches = [
                v for v in current if isinstance(v, dict) and v.get("token") == key
            ]
            current = matches[0] if len(matches) == 1 else None
        else:
            return None
    return current


def supported(spec, data):
    value = value_at(data, spec.path)
    if spec.platform == "switch":
        return type(value) in (int, bool) and value in (0, 1)
    if spec.platform == "number":
        return type(value) is int and spec.minimum <= value <= spec.maximum
    if spec.platform == "select":
        return value in spec.options
    return isinstance(value, str)


def settings_for(data, platform):
    specs = list(SETTINGS)
    for index, microphone in enumerate(data.get("microphones", [])):
        if not isinstance(microphone, dict) or not isinstance(
            microphone.get("token"), str
        ):
            continue
        token = microphone["token"]
        suffix = "" if len(data["microphones"]) == 1 else f" {index + 1}"
        specs.extend(
            (
                Setting(
                    f"microphone_{token}_volume",
                    f"Microphone{suffix} volume",
                    "number",
                    ("microphones", token, "level"),
                ),
                Setting(
                    f"microphone_{token}_mute",
                    f"Microphone{suffix} mute",
                    "switch",
                    ("microphones", token, "silent"),
                ),
            )
        )
    return [s for s in specs if s.platform == platform and supported(s, data)]
