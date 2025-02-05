import importlib
import logging
import pathlib

import click
import click_logging
from click_aliases import ClickAliasedGroup

from .. import __version__
from ..recording import Recording

DEFAULT_LOG_LEVEL = "INFO"


pass_recording = click.make_pass_decorator(Recording)
logger = logging.getLogger()


class PyavFilter(logging.Filter):
    def filter(self, record):
        if "forced frame type" in record.msg:
            if logger.getEffectiveLevel() >= logging.INFO:
                return False
        return True


logging.basicConfig(
    level=getattr(logging, DEFAULT_LOG_LEVEL),
    format="%(asctime)s.%(msecs)03d %(levelname).4s: %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("libav.libx264").addFilter(PyavFilter())


@click.option("--pdb/--no-pdb", default=False)
@click.option("--profile", is_flag=True)
@click_logging.simple_verbosity_option(logger, default=DEFAULT_LOG_LEVEL)
def cli(pdb, profile):
    click.echo(f"pikit version: {__version__}", err=True)
    click.echo(f"log level: {logging.getLevelName(logger)}", err=True)
    if profile:
        from . import profilinghook  # noqa
    if pdb:
        from . import pdbhook  # noqa


# we set the doc string here so that the command can output the version
cli.__doc__ = f""" Pupil Invisible Toolkit Version {__version__} """
cli = click.group(cls=ClickAliasedGroup)(cli)


@cli.group("recording", aliases=["rec"])
@click.option(
    "-r",
    "--recording-path",
    envvar="PIKIT_RECORDING_PATH",
    default=".",
    show_default=True,
    # type=click.Path(exists=True, file_okay=False),
)
@click.pass_context
def recording_cli(ctx, recording_path):
    recording = Recording(recording_path)
    ctx.obj = recording


for path in (pathlib.Path(__file__).parent / "commands").glob("*.py"):
    try:
        importlib.import_module(f".commands.{path.name[:-3]}", package="pikit.cli")
    except ImportError as e:
        click.echo(f"failed to load command: {path.name} ({e})", err=True)
