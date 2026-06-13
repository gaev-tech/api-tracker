"""apit — entrypoint."""

import typer

from apit import __version__
from apit.commands import history as history_cmd
from apit.commands import task as task_cmd

app = typer.Typer(
    name="apit",
    no_args_is_help=True,
    help="api-tracker CLI",
    rich_markup_mode="rich",
)
app.add_typer(task_cmd.app, name="task")
app.add_typer(history_cmd.app, name="history")


@app.command("version")
def version() -> None:
    """Показать версию CLI."""
    print(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
