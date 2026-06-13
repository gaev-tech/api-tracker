"""clite — entrypoint."""

from importlib.metadata import version as _pkg_version

import typer

from clite.commands import auth_cmd
from clite.commands import history as history_cmd
from clite.commands import project as project_cmd
from clite.commands import share as share_cmd
from clite.commands import task as task_cmd
from clite.commands import team as team_cmd

VERSION = _pkg_version("clite")

app = typer.Typer(
    name="clite",
    no_args_is_help=True,
    help="api-tracker CLI",
    rich_markup_mode="rich",
)
app.add_typer(task_cmd.app, name="task")
app.add_typer(history_cmd.app, name="history")
app.add_typer(team_cmd.app, name="team")
app.add_typer(project_cmd.app, name="project")
app.add_typer(share_cmd.app, name="share")
app.registered_commands.extend(auth_cmd.app.registered_commands)


@app.command("version")
def version() -> None:
    """Показать версию CLI."""
    print(VERSION)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
