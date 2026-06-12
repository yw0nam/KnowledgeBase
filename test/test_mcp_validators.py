"""Tests for kb.mcp.validators — pure functions, no DB needed."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from kb.mcp.validators import (
    NullableBool,
    NullableInt,
    NullableList,
    NullableStr,
    _coerce_none_string,
    require,
)

# ── _coerce_none_string ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["none", "None", "NONE", "null", "NULL", "Null", ""],
)
def test_coerce_none_string_returns_none(value: str) -> None:
    assert _coerce_none_string(value) is None


def test_coerce_none_string_strips_whitespace_before_compare() -> None:
    # "  " stripped → "" → in _NONE_STRINGS → None
    assert _coerce_none_string("  ") is None


def test_coerce_none_string_passthrough_normal_string() -> None:
    assert _coerce_none_string("hello") == "hello"


def test_coerce_none_string_passthrough_number() -> None:
    assert _coerce_none_string(42) == 42


def test_coerce_none_string_passthrough_already_none() -> None:
    # None itself is not a str so should pass through
    assert _coerce_none_string(None) is None


# ── Annotated types via pydantic models ───────────────────────────────────────


class _StrModel(BaseModel):
    v: NullableStr = None


class _BoolModel(BaseModel):
    v: NullableBool = None


class _IntModel(BaseModel):
    v: NullableInt = None


class _ListModel(BaseModel):
    v: NullableList = None


@pytest.mark.parametrize("raw", ["none", "null", "", "  "])
def test_nullable_str_coerces_to_none(raw: str) -> None:
    m = _StrModel(v=raw)
    assert m.v is None


def test_nullable_str_preserves_real_string() -> None:
    m = _StrModel(v="hello world")
    assert m.v == "hello world"


@pytest.mark.parametrize("raw", ["none", "null", ""])
def test_nullable_bool_coerces_to_none(raw: str) -> None:
    m = _BoolModel(v=raw)
    assert m.v is None


@pytest.mark.parametrize("raw", ["none", "null", ""])
def test_nullable_int_coerces_to_none(raw: str) -> None:
    m = _IntModel(v=raw)
    assert m.v is None


@pytest.mark.parametrize("raw", ["none", "null", ""])
def test_nullable_list_coerces_to_none(raw: str) -> None:
    m = _ListModel(v=raw)
    assert m.v is None


# ── require ───────────────────────────────────────────────────────────────────


def test_require_returns_none_when_all_present() -> None:
    result = require(a="x", b="y")
    assert result is None


def test_require_returns_error_when_field_is_none() -> None:
    result = require(a="x", b=None)
    assert result is not None
    assert "error" in result
    assert "b" in result["error"]


def test_require_returns_error_when_field_is_blank() -> None:
    result = require(a="  ")
    assert result is not None
    assert "error" in result
    assert "a" in result["error"]


def test_require_lists_all_missing_fields() -> None:
    result = require(x=None, y=None, z="present")
    assert result is not None
    error_msg = result["error"]
    assert "x" in error_msg
    assert "y" in error_msg
    assert "z" not in error_msg


def test_require_empty_string_treated_as_missing() -> None:
    result = require(field="")
    assert result is not None
    assert "field" in result["error"]
