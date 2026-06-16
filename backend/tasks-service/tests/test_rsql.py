import pytest

from tasks_service.models import Task
from tasks_service.rsql.fields import (
    FieldSpec,
    FieldType,
    RSQLContext,
    build_sqlalchemy_filter,
)
from tasks_service.rsql.parser import And, Comparison, Or, RSQLError, parse_rsql

TASK_FIELDS = [
    FieldSpec(name="status", column=Task.status, field_type=FieldType.STRING),
    FieldSpec(name="title", column=Task.title, field_type=FieldType.STRING),
    FieldSpec(name="labels", column=Task.labels, field_type=FieldType.STRING_ARRAY),
    FieldSpec(
        name="assignee", column=Task.assignee_id, field_type=FieldType.USER_EMAIL
    ),
    FieldSpec(name="created_at", column=Task.created_at, field_type=FieldType.DATETIME),
]


def _ctx_for(email: str = "solo@local") -> RSQLContext:
    fake_id = "a" * 40  # SHA1-hex placeholder
    return RSQLContext(
        current_user_email=email,
        resolve_email_to_user_id=lambda e: fake_id if e == email else None,
    )


# === parser ===


def test_parser_equality():
    ast = parse_rsql("status==open")
    assert isinstance(ast, Comparison)
    assert ast.field == "status" and ast.op == "==" and ast.value == "open"


def test_parser_and_or():
    ast = parse_rsql("status==open;labels=in=(bug,urgent)")
    assert isinstance(ast, And)
    assert len(ast.nodes) == 2


def test_parser_or():
    ast = parse_rsql("status==open,status==done")
    assert isinstance(ast, Or)


def test_parser_parens():
    ast = parse_rsql("(status==open,status==done);title!='x'")
    assert isinstance(ast, And)
    assert len(ast.nodes) == 2
    assert isinstance(ast.nodes[0], Or)


def test_parser_quoted_string():
    ast = parse_rsql("title=='hello world'")
    assert isinstance(ast, Comparison)
    assert ast.value == "hello world"


def test_parser_invalid_op():
    with pytest.raises(RSQLError):
        parse_rsql("status~~open")


def test_parser_unterminated_string():
    with pytest.raises(RSQLError):
        parse_rsql("title=='unclosed")


def test_parser_empty():
    with pytest.raises(RSQLError):
        parse_rsql("")


# === builder ===


def test_builder_equality():
    expr = build_sqlalchemy_filter("status==open", TASK_FIELDS, _ctx_for())
    rendered = str(expr.compile(compile_kwargs={"literal_binds": True}))
    assert "tasks.status = 'open'" in rendered


def test_builder_in_array():
    expr = build_sqlalchemy_filter("labels=in=(bug,urgent)", TASK_FIELDS, _ctx_for())
    rendered = str(expr.compile(compile_kwargs={"literal_binds": True}))
    assert "&&" in rendered


def test_builder_me_literal():
    expr = build_sqlalchemy_filter("assignee==me", TASK_FIELDS, _ctx_for("solo@local"))
    rendered = str(expr.compile(compile_kwargs={"literal_binds": True}))
    assert "tasks.assignee_id" in rendered


def test_builder_unknown_field():
    with pytest.raises(RSQLError, match=r"unknown field"):
        build_sqlalchemy_filter("foo==1", TASK_FIELDS, _ctx_for())


def test_builder_wrong_op_for_type():
    with pytest.raises(RSQLError, match=r"operator .* not allowed"):
        build_sqlalchemy_filter("title=gt=x", TASK_FIELDS, _ctx_for())
