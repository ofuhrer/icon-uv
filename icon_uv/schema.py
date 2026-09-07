"""Select the published daily JSON contract without a runtime validator dependency."""

import json
import re
from collections.abc import Mapping
from datetime import datetime
from importlib.resources import files


SCHEMA_VERSIONS = ("daily-uv-v1", "daily-uv-v2", "daily-uv-v3", "daily-uv-v4")


def load_schema(version_or_payload):
    """Return a fresh schema for a version string or a daily payload mapping.

    Unknown versions raise ValueError. Payload data never becomes a file path.
    """
    version = (version_or_payload.get("schema_version")
               if isinstance(version_or_payload, Mapping) else version_or_payload)
    if not isinstance(version, str) or version not in SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported daily schema version {version!r}; expected {', '.join(SCHEMA_VERSIONS)}")
    return json.loads((files("icon_uv") / "data" / f"{version}.schema.json").read_text(encoding="utf-8"))


def validate_daily(payload):
    """Validate structure and date/time formats using optional ``jsonschema``.

    Install ``jsonschema`` (included in the development environment) to use this
    helper. This does not check freshness or cross-field scientific semantics.
    Validation errors are jsonschema.ValidationError; success returns None.
    """
    schema = load_schema(payload)
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise ImportError("validate_daily requires jsonschema; install it with 'pip install jsonschema'") from exc
    checker = FormatChecker()

    @checker.checks("date-time", raises=ValueError)
    def date_time(value):
        # jsonschema's RFC3339 checker is an optional extra. Our published
        # timestamps must still be checked in a plain jsonschema installation.
        if not isinstance(value, str):
            return True
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value):
            return False
        return datetime.fromisoformat(value.upper()).tzinfo is not None

    Draft202012Validator(schema, format_checker=checker).validate(payload)
