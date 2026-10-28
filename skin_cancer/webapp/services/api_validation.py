"""Shared validation helpers for JSON API routes."""

from flask import abort, request


def json_object_or_400() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(
            400,
            description="Payload JSON phải là một object.",
        )
    return payload
