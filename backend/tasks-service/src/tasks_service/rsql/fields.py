"""Конвертер RSQL AST → SQLAlchemy expression, c whitelist полей и проверкой типов."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import ColumnElement, and_, false, or_
from sqlalchemy.sql.elements import ColumnClause

from tasks_service.rsql.parser import And, Comparison, Node, Op, Or, RSQLError, parse_rsql

type ValueCoercer = Callable[[object], object]


class FieldType(StrEnum):
    STRING = "string"
    INT = "int"
    DATETIME = "datetime"
    UUID = "uuid"
    USER_EMAIL = "user_email"
    STRING_ARRAY = "string_array"


# Какие операторы допустимы для каждого типа.
_OPS_BY_TYPE: dict[FieldType, set[Op]] = {
    FieldType.STRING: {"==", "!=", "=in=", "=out="},
    FieldType.INT: {"==", "!=", "=gt=", "=ge=", "=lt=", "=le=", "=in=", "=out="},
    FieldType.DATETIME: {"==", "!=", "=gt=", "=ge=", "=lt=", "=le="},
    FieldType.UUID: {"==", "!=", "=in=", "=out="},
    FieldType.USER_EMAIL: {"==", "!=", "=in=", "=out="},
    FieldType.STRING_ARRAY: {"=in=", "=out="},
}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    column: ColumnClause[object] | object
    field_type: FieldType


@dataclass(frozen=True)
class RSQLContext:
    """Контекст резолва: `me` → user_email, email → user_id и т.п."""

    current_user_email: str
    resolve_email_to_user_id: Callable[[str], UUID | None] | None = None


def _coerce_value(value: object, field_type: FieldType, ctx: RSQLContext) -> object:
    if field_type is FieldType.STRING:
        if not isinstance(value, str):
            raise RSQLError(f"expected string, got {value!r}")
        return value
    if field_type is FieldType.INT:
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise RSQLError(f"expected integer, got {value!r}")
    if field_type is FieldType.DATETIME:
        if not isinstance(value, str):
            raise RSQLError(f"expected ISO-8601 string, got {value!r}")
        try:
            return datetime.fromisoformat(value)
        except ValueError as e:
            raise RSQLError(f"invalid datetime {value!r}") from e
    if field_type is FieldType.UUID:
        if not isinstance(value, str):
            raise RSQLError(f"expected UUID string, got {value!r}")
        try:
            return UUID(value)
        except ValueError as e:
            raise RSQLError(f"invalid UUID {value!r}") from e
    if field_type is FieldType.USER_EMAIL:
        if value == "me":
            if ctx.resolve_email_to_user_id is None:
                raise RSQLError("`me` literal not allowed in this context")
            uid = ctx.resolve_email_to_user_id(ctx.current_user_email)
            if uid is None:
                raise RSQLError(f"current user {ctx.current_user_email} not found")
            return uid
        if not isinstance(value, str):
            raise RSQLError(f"expected email or `me`, got {value!r}")
        if ctx.resolve_email_to_user_id is None:
            raise RSQLError("email resolution not configured")
        uid = ctx.resolve_email_to_user_id(value)
        if uid is None:
            raise RSQLError(f"user {value!r} not found")
        return uid
    if field_type is FieldType.STRING_ARRAY:
        if not isinstance(value, str):
            raise RSQLError(f"expected string for array filter, got {value!r}")
        return value
    raise RSQLError(f"unsupported field type {field_type}")


def _build_comparison(
    comp: Comparison, specs: dict[str, FieldSpec], ctx: RSQLContext
) -> ColumnElement[bool]:
    spec = specs.get(comp.field)
    if spec is None:
        raise RSQLError(f"unknown field {comp.field!r}")
    if comp.op not in _OPS_BY_TYPE[spec.field_type]:
        raise RSQLError(f"operator {comp.op} not allowed for field {comp.field!r}")
    col = spec.column

    if comp.op in ("=in=", "=out="):
        if not isinstance(comp.value, tuple):
            raise RSQLError(f"expected list for {comp.op}")
        coerced = [_coerce_value(v, spec.field_type, ctx) for v in comp.value]
        if spec.field_type is FieldType.STRING_ARRAY:
            # labels=in=(bug,urgent) → labels && ARRAY['bug','urgent']
            expr = col.op("&&")(coerced)  # type: ignore[union-attr]
            return expr if comp.op == "=in=" else ~expr
        if comp.op == "=in=":
            return col.in_(coerced)  # type: ignore[union-attr]
        return col.not_in(coerced)  # type: ignore[union-attr]

    coerced_value = _coerce_value(comp.value, spec.field_type, ctx)
    if comp.op == "==":
        return col == coerced_value  # type: ignore[return-value]
    if comp.op == "!=":
        return col != coerced_value  # type: ignore[return-value]
    if comp.op == "=gt=":
        return col > coerced_value  # type: ignore[operator]
    if comp.op == "=ge=":
        return col >= coerced_value  # type: ignore[operator]
    if comp.op == "=lt=":
        return col < coerced_value  # type: ignore[operator]
    if comp.op == "=le=":
        return col <= coerced_value  # type: ignore[operator]
    raise RSQLError(f"unknown operator {comp.op}")


def _build(node: Node, specs: dict[str, FieldSpec], ctx: RSQLContext) -> ColumnElement[bool]:
    if isinstance(node, Comparison):
        return _build_comparison(node, specs, ctx)
    if isinstance(node, And):
        return and_(*(_build(n, specs, ctx) for n in node.nodes))
    if isinstance(node, Or):
        return or_(*(_build(n, specs, ctx) for n in node.nodes))
    raise RSQLError(f"unsupported node type {type(node).__name__}")


def build_sqlalchemy_filter(
    source: str,
    specs: Sequence[FieldSpec],
    ctx: RSQLContext,
) -> ColumnElement[bool]:
    """Парсит RSQL и собирает SQLAlchemy where-выражение."""
    spec_map = {s.name: s for s in specs}
    try:
        ast = parse_rsql(source)
    except RSQLError:
        raise
    if not spec_map:
        return false()
    return _build(ast, spec_map, ctx)
