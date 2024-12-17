from datetime import datetime
import logging

def get_time_from_alert_file(alert_file_name):
    """Get the incident start time from an alert file"""
    try:
        with open(alert_file_name, "r") as file:
            # Read first line and extract time
            first_line = file.readline().strip()
            if first_line:
                return first_line.split("at ")[-1].strip()
            return None
    except FileNotFoundError:
        logging.error(f"Error: File {alert_file_name} not found")
        return None
    except Exception as e:
        logging.error(f"Error reading file: {e}")
        return None


def convert_time_to_timestamp(time_str: str) -> float:
    """
    Convert a time string in format 'YYYY-MM-DD HH:MM:SS' to Unix timestamp.

    Args:
        time_str: String representation of time in format 'YYYY-MM-DD HH:MM:SS'

    Returns:
        float: Unix timestamp
    """
    try:
        dt_object = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return dt_object.timestamp()
    except ValueError as e:
        logging.error(f"Error converting time string: {e}")
        return None


def format_duration(seconds: float) -> str:
    """
    Convert seconds into a human-readable duration string.

    Args:
        seconds: Number of seconds (float)

    Returns:
        str: Formatted string like "2 days 4 hours 4 minutes 53 secs"
    """
    days, remainder = divmod(int(seconds), 86400)  # 86400 seconds in a day
    hours, remainder = divmod(remainder, 3600)  # 3600 seconds in an hour
    minutes, secs = divmod(remainder, 60)  # 60 seconds in a minute

    parts = []
    if days > 0:
        parts.append(f"{days} {'day' if days == 1 else 'days'}")
    if hours > 0:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes > 0:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    if (
        secs > 0 or not parts
    ):  # Include seconds if it's non-zero or if no larger units exist
        parts.append(f"{secs} {'sec' if secs == 1 else 'secs'}")

    return " ".join(parts)
