import csv
import json
import os
import struct

import tabulate

RAW_FORMATS = [
    "<Q",  # unsigned little endian int64 (timestamps)
    "<2f",  # 2 little endian float values (x, y coords in video)
    "<6f",  # 6 little endian float values (gyro/accel values)
]

EXPORT_FORMATS = ["tsv", "csv", "json", "pretty"]


def row_writer(outfile, row_generator, keys, format):
    """
    Function to output a list of dicts in rows in a `format`

    Args:
        outfile: file to write output to
        row_generator: generator function that yields dicts to print
        keys: dict keys to output
        format: One of 'csv', 'tsv', 'json', 'pretty'

    Examples:
        >>> def row_generator():
        ...     for n in range(2):
        ...         yield { "n": n, "squared": n * 2 }
        >>> row_writer(sys.stdout, row_generator, ['n', 'squared'], 'tsv')
        i   squared
        0   0
        1   1
        2   4
        3   9
    """

    if format not in EXPORT_FORMATS + RAW_FORMATS:
        raise ValueError(f"unknown format: {format}")

    if format in ("csv", "tsv"):
        delimiter = {"csv": ",", "tsv": "\t"}[format]
        writer = csv.DictWriter(
            outfile,
            delimiter=delimiter,
            lineterminator=os.linesep,
            fieldnames=keys,
            quotechar="'",
        )
        writer.writeheader()
        for row in row_generator():
            writer.writerow({key: row[key] for key in keys})
        return

    if format == "json":
        outfile.write("[\n")
        for row in row_generator():
            outfile.write(
                json.dumps({key: value for key, value in row.items()}) + ",\n"
            )
        outfile.write("]\n")
        return

    if format == "jsonlines":
        for row in row_generator():
            outfile.write(json.dumps({key: value for key, value in row.items()}) + "\n")
        return

    if format in RAW_FORMATS:
        for row in row_generator():
            outfile.write(struct.pack(format, *[row[key] for key in keys]))
        return

    def _tabulate_row_generator():
        for row in row_generator():
            yield [row[key] for key in keys]

    def pdtabulate(rows):
        return tabulate.tabulate(rows, headers=keys, tablefmt=format)

    outfile.write(pdtabulate(_tabulate_row_generator()) + "\n")
