"""RSQL parser v1 (architecture.md §8, product.md §7.1.3).

Поддерживаемая грамматика:
  query := or_expr
  or_expr := and_expr (',' and_expr)*
  and_expr := atom (';' atom)*
  atom := '(' or_expr ')' | comparison
  comparison := IDENT OP value
  OP := '==' | '!=' | '=gt=' | '=ge=' | '=lt=' | '=le=' | '=in=' | '=out='
  value := scalar | list
  scalar := STRING | NUMBER | IDENT
  list := '(' scalar (',' scalar)* ')'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


class RSQLError(ValueError):
    """Невалидный RSQL — некорректный синтаксис, неизвестный оператор и т.п."""


Op = Literal["==", "!=", "=gt=", "=ge=", "=lt=", "=le=", "=in=", "=out="]


@dataclass(frozen=True)
class Comparison:
    field: str
    op: Op
    value: object


@dataclass(frozen=True)
class And:
    nodes: tuple[Node, ...]


@dataclass(frozen=True)
class Or:
    nodes: tuple[Node, ...]


Node = Comparison | And | Or


_OPS: tuple[str, ...] = ("==", "!=", "=gt=", "=ge=", "=lt=", "=le=", "=in=", "=out=")


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0

    def parse(self) -> Node:
        node = self._or()
        self._skip_ws()
        if self.pos != len(self.source):
            raise RSQLError(
                f"unexpected char at pos {self.pos}: {self.source[self.pos]!r}"
            )
        return node

    # OR-уровень — самый низкий приоритет
    def _or(self) -> Node:
        nodes: list[Node] = [self._and()]
        while True:
            self._skip_ws()
            if self.pos < len(self.source) and self.source[self.pos] == ",":
                self.pos += 1
                nodes.append(self._and())
            else:
                break
        return nodes[0] if len(nodes) == 1 else Or(tuple(nodes))

    # AND-уровень
    def _and(self) -> Node:
        nodes: list[Node] = [self._atom()]
        while True:
            self._skip_ws()
            if self.pos < len(self.source) and self.source[self.pos] == ";":
                self.pos += 1
                nodes.append(self._atom())
            else:
                break
        return nodes[0] if len(nodes) == 1 else And(tuple(nodes))

    def _atom(self) -> Node:
        self._skip_ws()
        if self.pos >= len(self.source):
            raise RSQLError(f"unexpected end at position {self.pos}")
        if self.source[self.pos] == "(":
            self.pos += 1
            node = self._or()
            self._skip_ws()
            if self.pos >= len(self.source) or self.source[self.pos] != ")":
                raise RSQLError(f"expected ')' at position {self.pos}")
            self.pos += 1
            return node
        return self._comparison()

    def _comparison(self) -> Comparison:
        field = self._ident()
        self._skip_ws()
        op = self._op()
        value = self._value(op)
        return Comparison(field=field, op=op, value=value)

    def _ident(self) -> str:
        self._skip_ws()
        start = self.pos
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch.isalnum() or ch == "_":
                self.pos += 1
            else:
                break
        if start == self.pos:
            raise RSQLError(f"expected identifier at position {start}")
        return self.source[start : self.pos]

    def _op(self) -> Op:
        for cand in _OPS:
            if self.source.startswith(cand, self.pos):
                self.pos += len(cand)
                return cand  # type: ignore[return-value]
        snippet = self.source[self.pos : self.pos + 6]
        raise RSQLError(f"expected operator at position {self.pos} (got {snippet!r})")

    def _value(self, op: Op) -> object:
        self._skip_ws()
        if op in ("=in=", "=out="):
            return self._list()
        return self._scalar()

    def _list(self) -> tuple[object, ...]:
        if self.pos >= len(self.source) or self.source[self.pos] != "(":
            raise RSQLError(f"expected '(' for list at position {self.pos}")
        self.pos += 1
        items: list[object] = []
        while True:
            self._skip_ws()
            items.append(self._scalar())
            self._skip_ws()
            if self.pos < len(self.source) and self.source[self.pos] == ",":
                self.pos += 1
                continue
            break
        if self.pos >= len(self.source) or self.source[self.pos] != ")":
            raise RSQLError(f"expected ')' for list at position {self.pos}")
        self.pos += 1
        return tuple(items)

    def _scalar(self) -> object:
        self._skip_ws()
        if self.pos >= len(self.source):
            raise RSQLError(f"expected value at position {self.pos}")
        ch = self.source[self.pos]
        if ch in ("'", '"'):
            return self._string(ch)
        if ch == "-" or ch.isdigit():
            return self._number()
        return self._ident()

    def _string(self, quote: str) -> str:
        self.pos += 1
        start = self.pos
        result: list[str] = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == "\\" and self.pos + 1 < len(self.source):
                result.append(self.source[self.pos + 1])
                self.pos += 2
                continue
            if ch == quote:
                self.pos += 1
                return "".join(result) if result else self.source[start : self.pos - 1]
            result.append(ch)
            self.pos += 1
        raise RSQLError(f"unterminated string from position {start - 1}")

    def _number(self) -> int | float:
        start = self.pos
        if self.source[self.pos] == "-":
            self.pos += 1
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            self.pos += 1
        is_float = False
        if self.pos < len(self.source) and self.source[self.pos] == ".":
            is_float = True
            self.pos += 1
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                self.pos += 1
        text = self.source[start : self.pos]
        try:
            return float(text) if is_float else int(text)
        except ValueError as e:
            raise RSQLError(f"invalid number at position {start}: {text!r}") from e

    def _skip_ws(self) -> None:
        while self.pos < len(self.source) and self.source[self.pos] in " \t\n\r":
            self.pos += 1


def parse_rsql(source: str) -> Node:
    """Парсит RSQL-строку в AST."""
    if not source or not source.strip():
        raise RSQLError("empty RSQL filter")
    return _Parser(source).parse()
