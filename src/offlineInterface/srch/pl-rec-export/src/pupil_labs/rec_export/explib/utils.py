import argparse
import ast
import inspect
from itertools import chain

import numpy as np
import typeguard


def closest_matches(points1, points2, max_dispersion=1 / 100.0, return_indices=False):
    def find_nearest_idx(array, value):
        idx = np.searchsorted(array, value, side="left")
        try:
            if abs(value - array[idx - 1]) < abs(value - array[idx]):
                return idx - 1
            else:
                return idx
        except IndexError:
            return idx - 1

    matched = []
    if len(points2):
        for p1_idx, p1 in enumerate(points1):
            p2_idx = find_nearest_idx(points2, p1)
            p2 = points2[p2_idx]
            dispersion = max(p1, p2) - min(p1, p2)
            if dispersion < max_dispersion:
                if return_indices:
                    matched.append((p1_idx, p2_idx))
                else:
                    matched.append((p1, p2))
            else:
                pass

    return matched


def iter_with_next(iterable, last_marker=None):
    """
    Yields (item, next_item) for item in an iterable

    Args:
        iterable (iterable): items to process
        last_marker (Any): value to return for next_item of the last item

    Examples:
        >>> for item, next_item in iter_with_next(range(3), last_marker="last"):
        ...     print((item, next_item))
        (0, 1)
        (1, 2)
        (2, 'last')

    """
    count = 0
    previous_item = last_marker
    for item in iterable:
        if count > 0:
            yield previous_item, item
        previous_item = item
        count += 1
    if count > 0:
        yield previous_item, last_marker


def convert_arg(arg_name, arg_type):
    """
    Takes a string and a type and returns a function that can be used to convert
    """

    def wrapped(value):
        if arg_type != str:
            try:
                value = ast.literal_eval(value)
            except Exception:
                raise
        try:
            typeguard.check_type(arg_name, value, arg_type)
        except Exception as e:
            raise argparse.ArgumentTypeError(str(e))
        return value

    wrapped.__name__ = f"{arg_type}"
    return wrapped


def argparser_from_class(AnnotatedClass):
    """
    Creates an argparser spec by insectping an annotated class

    Args:
        AnnotatedClass: Any class with

    Returns:
        parser argparse.ArgumentParser: An arg parser based on AnnotatedClass

    Example:
        >>> class Params(typing.NamedTuple):
        ...     some_boolean: bool = True
        ...     some_value: float = 4.3
        >>> parser = argparser_from_namedtuple(Params)
        >>> parser.parse_args()
        Namespace(some_boolean=True, some_value=4.3)
    """
    source = inspect.getsource(AnnotatedClass)

    field_comments = {}
    for line in source.splitlines():
        if "=" not in line:
            continue
        key = line.split("=")[0]
        key = key.split(":")[0]
        key = key.strip()

        parts = line.split("#", 1)
        if len(parts) > 1:
            field_comments[key] = parts[1]

    parser = argparse.ArgumentParser(
        description=f"{AnnotatedClass.__name__} args",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    signature = inspect.signature(AnnotatedClass)
    for attr, param in signature.parameters.items():
        if param.annotation == bool:
            parser.add_argument(
                "--" + param.name.replace("_", "-"),
                help=field_comments.get(attr),
                type=param.annotation,
                default=param.default,
                action=argparse.BooleanOptionalAction,
            )
        else:
            parser.add_argument(
                "--" + param.name.replace("_", "-"),
                help=field_comments.get(attr),
                type=convert_arg(param.name, param.annotation),
                # type=param.annotation,
                default=param.default,
            )
    return parser


def skip_non_monotonic(iterable):
    """
    Will yield values for an iterable only if the value was monotonically
    increasing

    Examples:

        >>> list(skip_non_monotonic([1,2,2,5,4,4,5,6]))
        [1, 2, 5, 6]
    """
    previous_item = sentinel = object()
    for item in iterable:
        if previous_item is not sentinel and previous_item >= item:
            continue
        yield item
        previous_item = item


def closest_matches_iterative(
    values_a,
    values_b,
    max_dispersion=int(1e9 // 200),
    key=lambda x: x,
):
    """
    For each item in values_a yields the closest item from values_b using
    key(a) and key(b) as the key function, within max_dispersion

    This function requires that both values_a and values_b contain
    monotonically increasing items.

    Args:
        values_a: an iterable of sequential values
        values_b: an iterable of sequential values
        max_dispersion: threshold to consider when matching items
        key: function to extract the sequence key from either iterable

    Examples:
        >>> list(closest_matches_iterative([10, 15, 20], [ 12, 13, 14, 19]))
        [(10, 12), (15, 14), (20, 19)]
        >>> list(closest_matches_iterative([3, 4, 5, 6, 7], [4, 5]))
        [(3, 4), (4, 4), (5, 5), (6, 5), (7, 5)]
        >>> list(closest_matches_iterative([3, 4, 5, 6, 7], [4, 5], max_dispersion=1))
        [(3, 4), (4, 4), (5, 5), (6, 5)]
        >>> list(closest_matches_iterative([1, 2, 3, 4], [1, 2, 3, 4]))
        [(1, 1), (2, 2), (3, 3), (4, 4)]
        >>> list(closest_matches_iterative(\
            [(1.6, 'a1'), (2.2, 'a2'), (3.3, 'a3')],\
            [(0.9, 'b1'), (1.9, 'b2')],\
            key=lambda x: int(x[0])\
        ))
        [((1.6, 'a1'), (1.9, 'b2'))]
        >>> list(closest_matches_iterative([], [1, 2, 3]))
        []
        >>> list(closest_matches_iterative([1, 2, 3], []))
        []
        >>> list(closest_matches_iterative([], []))
        []
        >>> list(closest_matches_iterative([1], [2]))
        [(1, 2)]
        >>> list(closest_matches_iterative([1], []))
        []
    """
    prev = []
    iterable_values_b = iter(values_b)
    prev_a_key = None
    for a in values_a:
        a_key = key(a)
        if prev_a_key is not None and prev_a_key >= a_key:
            raise Exception(f"value a is not monotonic: {prev_a_key} >= {a_key}")

        iterable_values_b_with_prev = chain(prev, iterable_values_b)
        for b, next_b in iter_with_next(iterable_values_b_with_prev):
            b_key = key(b)
            delta = abs(a_key - b_key)
            if next_b is None:
                if delta <= max_dispersion:
                    yield a, b
                break

            next_b_key = key(next_b)
            if b_key >= next_b_key:
                raise Exception(f"value b is not monotonic: {b_key} >= {next_b_key}")

            next_delta = abs(a_key - next_b_key)
            if next_delta > delta:
                if delta <= max_dispersion:
                    yield a, b
                prev = [b, next_b]
                break
        else:
            break

        prev_a_key = a_key


def matched_stream_samples(stream_a, stream_b, max_dispersion=int(1e9 // 200)):
    def _get_sample_timestamp(sample):
        timestamp, frame = sample
        return timestamp

    yield from closest_matches_iterative(
        stream_a,
        stream_b,
        max_dispersion=max_dispersion,
        key=_get_sample_timestamp,
    )
