from datetime import datetime


def time_ago(now: datetime, past: datetime | None, seconds_before_just_now: float=5) -> str:
    """
    Returns a human-readable string representing the time elapsed since the given past datetime.

    Parameters
    ----------
    now : datetime
        The current datetime.
    past : datetime | None
        The past datetime to compare against.
    seconds_before_just_now : float, optional
        The threshold in seconds below which the function will return "<{seconds_before_just_now}s ago". Default is 5.

    Returns
    -------
    str
        A human-readable string representing the time elapsed since the given past datetime.
    """
    if not past:
        return " 00? ago"
    delta = now - past
    seconds = delta.total_seconds()

    if seconds < seconds_before_just_now + 1: # Add 1 second to account for rounding issues
        return f"<{int(seconds_before_just_now):>2}s ago"

    if seconds < 60:
        value, unit = int(seconds), "s"
    elif seconds < 3600:
        value, unit = int(seconds // 60), "m"
    elif seconds < 86400:
        value, unit = int(seconds // 3600), "h"
    else:
        value, unit = int(seconds // 86400), "d"

    return f" {value:>2}{unit} ago"

def format_date(date: datetime | None) -> str:
    if not date:
        return "N/A"
    date = date.astimezone()  # Convert to local timezone
    now = datetime.now().astimezone()  # Current time in local timezone
    if (now - date).days < 1:
        return date.strftime("%H:%M:%S")
    return date.strftime("%Y-%m-%d %H:%M:%S")

def short_recording_id(recording_id: str) -> str:
    return f"{recording_id[:8]}..." if recording_id else "N/A"