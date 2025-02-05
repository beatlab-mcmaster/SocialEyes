def iter_with_next(iterable, last_marker=None):
    """
    Yields (item, next_item) for item in an iterable

    Args:
        iterable (iterable): items to process
        last_marker (Any): value to return for next_item of the last item

    Examples:
        >>> for item, next_item in with_next(range(3), last_marker="last"):
        ...     print(item, next_item)
        (0, 1)
        (1, 2)
        (3, "last")

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
