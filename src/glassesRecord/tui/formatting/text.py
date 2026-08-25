from typing import Optional
from datetime import datetime

def time_ago(now: datetime, past: Optional[datetime], exact_seconds_threshold: int=5) -> str:
    """
    Returns a human-readable string representing the time elapsed since the given past datetime.

    Parameters
    ----------
    now : datetime
        The current datetime.
    past : Optional[datetime]
        The past datetime to compare against.
    exact_seconds_threshold : int, optional
        The threshold in seconds below which the function will return "just now". Default is 5.

    Returns
    -------
    str
        A human-readable string representing the time elapsed since the given past datetime.
    """
    if not past:
        return "Never"
    delta = now - past
    seconds = delta.total_seconds()
    if seconds < exact_seconds_threshold:
        return "just now"
    if seconds < 60:
        return f"{int(seconds):>2}s ago"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes:>2}m ago"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours:>2}h ago"
    else:
        days = int(seconds // 86400)
        return f"{days:>2}d ago"

def format_date(date: Optional[datetime]) -> str:
    if not date:
        return "N/A"
    date = date.astimezone()  # Convert to local timezone
    now = datetime.now().astimezone()  # Current time in local timezone
    if (now - date).days < 1:
        return date.strftime("%H:%M:%S")
    return date.strftime("%Y-%m-%d %H:%M:%S")

def short_recording_id(recording_id: str) -> str:
    return f"{recording_id[:8]}..." if recording_id else "N/A"