"""clite — entrypoint. Verb-first command structure (v2.0.0)."""

from importlib.metadata import version as _pkg_version

import typer

from clite.commands import (
    add_cmd,
    auth_cmd,
    create_cmd,
    get_cmd,
    leave_cmd,
    rename_cmd,
    update_cmd,
)

VERSION = _pkg_version("clite")

app = typer.Typer(
    name="clite",
    no_args_is_help=True,
    help="api-tracker CLI",
    rich_markup_mode="rich",
)

app.add_typer(get_cmd.app, name="get")
app.add_typer(create_cmd.app, name="create")
app.add_typer(update_cmd.app, name="update")
app.add_typer(rename_cmd.app, name="rename")
app.add_typer(leave_cmd.app, name="leave")
app.add_typer(add_cmd.app, name="add")

# login / logout / me — на верхнем уровне.
app.registered_commands.extend(auth_cmd.app.registered_commands)


@app.command("version")
def version() -> None:
    """Показать версию CLI."""
    print(VERSION)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
