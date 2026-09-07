"""Load the authoritative daily JSON contract without a runtime validator dependency."""

import hashlib
import json
import re
from datetime import datetime
from importlib.resources import files


SCHEMA_NAME = 'daily-uv'
_SCHEMA_BYTES = files('icon_uv').joinpath('data/daily-uv.schema.json').read_bytes()
CONTRACT_SHA256 = hashlib.sha256(_SCHEMA_BYTES).hexdigest()


def load_schema():
    """Return an independent copy of the single daily product schema."""
    return json.loads(_SCHEMA_BYTES)


def validate_daily(payload):
    """Validate structure and date/time formats using optional ``jsonschema``.

    Install ``jsonschema`` (included in the development environment) to use this
    helper. This does not check freshness or cross-field scientific semantics.
    Validation errors are jsonschema.ValidationError; success returns None.
    """
    schema = load_schema()
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
