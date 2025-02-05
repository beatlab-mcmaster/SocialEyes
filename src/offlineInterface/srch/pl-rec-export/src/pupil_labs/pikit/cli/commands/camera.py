import csv
import json

import click
import more_itertools
import tqdm

from ...lib.camera import PISceneCamera
from .. import cli

pass_camera = click.make_pass_decorator(PISceneCamera)


@cli.group("camera")
@click.argument("serial_number", type=str)
@click.pass_context
def camera_cli(ctx, serial_number):
    camera = PISceneCamera.load(serial_number)
    ctx.obj = camera


@camera_cli.command()
@click.option("-v", "--version", default="v1", show_default=True)
@click.option(
    "-f",
    "--format",
    default="json",
    type=click.Choice(["json", "binary"], case_sensitive=False),
    show_default=True,
)
@pass_camera
def calibration(camera, version="v1", format="json"):
    format = format.lower()
    if format == "json":
        click.echo(json.dumps(camera.as_v1_calibration_json(), indent=2))
    if format == "binary":
        click.echo(camera.as_v1_calibration_binary())


@camera_cli.command()
@click.option("-i", "--infile", type=click.File("r"), default="-", show_default=True)
@click.option("-o", "--outfile", type=click.File("w"), default="-", show_default=True)
@pass_camera
def normalize(camera: PISceneCamera, infile, outfile):
    batchsize = 200000
    points = ((float(row[0]), float(row[1])) for row in (csv.reader(infile)))
    normalize = camera.normalize_points

    writer = csv.writer(outfile)
    with tqdm.tqdm() as progress:
        for batch in more_itertools.chunked(points, n=batchsize):
            for normalized_point in normalize(batch):
                writer.writerow([normalized_point[0], normalized_point[1]])
                progress.update(1)


@camera_cli.command()
@click.option("-i", "--infile", type=click.File("r"), default="-", show_default=True)
@click.option("-o", "--outfile", type=click.File("w"), default="-", show_default=True)
@pass_camera
def rectify(camera: PISceneCamera, infile, outfile):
    batchsize = 200000
    points = ((float(row[0]), float(row[1])) for row in (csv.reader(infile)))
    rectify = camera.rectify_points

    writer = csv.writer(outfile)
    with tqdm.tqdm() as progress:
        for batch in more_itertools.chunked(points, n=batchsize):
            for rectified_point in rectify(batch):
                writer.writerow([rectified_point[0], rectified_point[1]])
                progress.update(1)


@camera_cli.command()
@click.option("-i", "--infile", type=click.File("r"), default="-", show_default=True)
@click.option("-o", "--outfile", type=click.File("w"), default="-", show_default=True)
@pass_camera
def distort(camera: PISceneCamera, infile, outfile):
    batchsize = 200000
    points = ((float(row[0]), float(row[1])) for row in (csv.reader(infile)))
    distort = camera.distort_points

    writer = csv.writer(outfile)
    with tqdm.tqdm() as progress:
        for batch in more_itertools.chunked(points, n=batchsize):
            for distorted_point in distort(batch):
                writer.writerow([distorted_point[0], distorted_point[1]])
                progress.update(1)
