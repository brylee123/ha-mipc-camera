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
    translation_key: str | None = None
    translation_placeholders: dict[str, str] | None = None


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
    Setting("osd_date", "OSD calendar date", "switch", ("osd", "date", "date_enable")),
    Setting("osd_time", "OSD clock time", "switch", ("osd", "date", "time_enable")),
    Setting(
        "recording",
        "SD recording enabled",
        "switch",
        ("recording", "task", "sch", "enable"),
    ),
    Setting(
        "day_night",
        "Day/night mode",
        "select",
        ("imaging", "mode"),
        options=("auto", "day", "night"),
    ),
    Setting("osd_weekday", "OSD weekday", "switch", ("osd", "week")),
    Setting(
        "motion_detection",
        "Motion alarm action",
        "switch",
        ("alert_actions", "actions", "motion_alert", "enable"),
    ),
    Setting("alarm_armed", "Alarm armed", "switch", ("alert_actions", "enable")),
    Setting(
        "osd_date_format",
        "OSD date format",
        "select",
        ("osd", "date", "format"),
        options=("YYYY-MM-DD", "MM-DD-YYYY"),
    ),
    Setting(
        "osd_time_format",
        "OSD time format",
        "select",
        ("controls", "time_format"),
        options=("24_hour", "12_hour"),
    ),
    Setting(
        "power_frequency",
        "Power frequency",
        "select",
        ("controls", "power_frequency"),
        options=("60_hz", "50_hz"),
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
                    translation_key="microphone_volume",
                    translation_placeholders={"suffix": suffix},
                ),
                Setting(
                    f"microphone_{token}_mute",
                    f"Microphone{suffix} mute",
                    "switch",
                    ("microphones", token, "silent"),
                    translation_key="microphone_mute",
                    translation_placeholders={"suffix": suffix},
                ),
            )
        )
    zones = data.get("timezones")
    if isinstance(zones, list) and zones and all(isinstance(z, str) for z in zones):
        specs.append(
            Setting(
                "timezone",
                "Timezone",
                "select",
                ("ntp", "timezone"),
                options=tuple(zones),
            )
        )
    recording = value_at(data, ("recording", "task", "sch"))
    if (
        isinstance(recording, dict)
        and type(recording.get("full_time")) in (bool, int)
        and recording["full_time"] in (0, 1)
    ):
        choices = (
            ("off", "continuous", "scheduled")
            if recording.get("times")
            else ("off", "continuous")
        )
        specs.append(
            Setting(
                "recording_mode",
                "SD recording mode",
                "select",
                ("controls", "recording_mode"),
                options=choices,
            )
        )
    return [s for s in specs if s.platform == platform and supported(s, data)]
