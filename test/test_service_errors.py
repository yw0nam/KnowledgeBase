"""Tests for kb.service.errors.ServiceError."""

from __future__ import annotations

import pytest


def test_service_error_attributes():
    from kb.service.errors import ServiceError

    err = ServiceError("conflict", "raw_source already exists")
    assert err.code == "conflict"
    assert err.detail == "raw_source already exists"


def test_service_error_str_contains_code_and_detail():
    from kb.service.errors import ServiceError

    err = ServiceError("not_found", "page not found")
    s = str(err)
    assert "not_found" in s
    assert "page not found" in s


def test_service_error_is_exception():
    from kb.service.errors import ServiceError

    with pytest.raises(ServiceError) as exc_info:
        raise ServiceError("lint_failed", {"errors": ["missing sources"]})
    assert exc_info.value.code == "lint_failed"
    assert exc_info.value.detail == {"errors": ["missing sources"]}


def test_service_error_rejects_invalid_code():
    from kb.service.errors import ServiceError

    with pytest.raises(ValueError):
        ServiceError("nonsense", "this code is not allowed")


def test_service_error_with_dict_detail():
    from kb.service.errors import ServiceError

    err = ServiceError("export_failed", {"file": "wiki/foo.md", "reason": "disk full"})
    assert err.code == "export_failed"
    assert err.detail["reason"] == "disk full"
    assert "export_failed" in str(err)
