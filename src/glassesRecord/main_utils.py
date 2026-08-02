from datetime import datetime
from typing import Optional
import numbers
from rich.text import Text
from rich.style import Style

def as_colored_text(val, **kwargs):
    """Convert a value into a Rich colored text representation.

    Args:
        val: The value to convert.
        **kwargs: Additional arguments for color styling.

    Returns:
        Text: A styled Text object based on the value.
    """
    if val is None:
        return '-'
    elif isinstance(val, bool):
        return Text(str(val), style=get_style_bool(val, kwargs.get('reverse', False)))
    elif isinstance(val, numbers.Number):
        if 'reverse' in kwargs and kwargs['reverse']:
            return Text(str(val), style=get_style_num(-val, -kwargs['thresh_low'], -kwargs['thresh_high']))
        else:
            return Text(str(val), style=get_style_num(val, kwargs['thresh_low'], kwargs['thresh_high']))
    else:
        return Text(str(val))

def get_style_num(val, thresh_low, thresh_high) -> Style:
    """Determine the style for numeric values based on thresholds.

    Args:
        val (float): The numeric value.
        thresh_low (float): The lower threshold.
        thresh_high (float): The upper threshold.

    Returns:
        Style: The style to apply based on the value.
    """
    if val == None:
        return Style()
    elif val <= thresh_low:
        return Style(color="red")
    elif thresh_high > val > thresh_low:
        return Style(color="yellow")
    elif val >= thresh_high:
        return Style(color="green")
    else:
        return Style()

def get_style_bool(val, reverse=False) -> Style:
    """Determine the style for boolean values.

    Args:
        val (bool or None): The boolean value to evaluate.

    Returns:
        Style: The style to apply based on the value:
             - green if True
             - red if False
             - default (empty) if None
    """
    if val == None:
        return Style()
    elif val:
        return Style(color="red") if reverse else Style(color="green")
    else:
        return Style(color="green") if reverse else Style(color="red")

def time_ago(now: datetime, past: Optional[datetime]) -> str:
    if not past:
        return "Never"
    delta = now - past
    seconds = delta.total_seconds()
    if seconds < 5:
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

def short_recording_id(recording_id: str) -> str:
    return f"{recording_id[:8]}..." if recording_id else "N/A"

def format_date(date: Optional[datetime]) -> str:
    if not date:
        return "N/A"
    date = date.astimezone()  # Convert to local timezone
    now = datetime.now().astimezone()  # Current time in local timezone
    if (now - date).days < 1:
        return date.strftime("%H:%M:%S")
    return date.strftime("%Y-%m-%d %H:%M:%S")