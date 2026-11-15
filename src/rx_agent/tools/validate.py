from __future__ import annotations

import json
from typing import Any


def _coerce(schema: dict[str, Any], value: Any, name: str) -> tuple[Any, str | None]:
    """Validate + gently coerce a value (weak models send "30" for 30, "true" for true)."""
    typ = schema.get("type")
    if typ == "string":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str):
            return None, f"'{name}' must be a string"
    elif typ == "integer":
        if isinstance(value, bool):
            return None, f"'{name}' must be an integer"
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value)
        if not isinstance(value, int):
            return None, f"'{name}' must be an integer"
    elif typ == "number":
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                return None, f"'{name}' must be a number"
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"'{name}' must be a number"
    elif typ == "boolean":
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            value = value.lower() == "true"
        if not isinstance(value, bool):
            return None, f"'{name}' must be true or false"
    elif typ == "array":
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return None, f"'{name}' must be an array"
        if not isinstance(value, list):
            return None, f"'{name}' must be an array"
        item_schema = schema.get("items")
        if item_schema:
            cleaned = []
            for i, item in enumerate(value):
                fixed, err = _coerce(item_schema, item, f"{name}[{i}]")
                if err:
                    return None, err
                cleaned.append(fixed)
            value = cleaned
    elif typ == "object":
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return None, f"'{name}' must be an object"
        if not isinstance(value, dict):
            return None, f"'{name}' must be an object"
        if "properties" in schema:
            value, err = validate_args(schema, value, prefix=f"{name}.")
            if err:
                return None, err
    if "enum" in schema and value not in schema["enum"]:
        return None, f"'{name}' must be one of {schema['enum']}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return None, f"'{name}' must be >= {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return None, f"'{name}' must be <= {schema['maximum']}"
    return value, None


def validate_args(schema: dict[str, Any], args: Any, prefix: str = "") -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(args, dict):
        return None, "arguments must be a JSON object"
    props: dict[str, Any] = schema.get("properties", {})
    errors: list[str] = []
    out: dict[str, Any] = {}
    for key in schema.get("required", []):
        if key not in args or args[key] is None:
            errors.append(f"missing required argument '{prefix}{key}'")
    for key, value in args.items():
        if key not in props:
            errors.append(f"unknown argument '{prefix}{key}' (allowed: {', '.join(props) or 'none'})")
            continue
        if value is None:
            continue
        fixed, err = _coerce(props[key], value, f"{prefix}{key}")
        if err:
            errors.append(err)
        else:
            out[key] = fixed
    if errors:
        return None, "; ".join(errors)
    return out, None
