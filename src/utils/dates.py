import re
from datetime import datetime

def parse_date(date_input):
    """Parse various date formats and return (date_str, time_str)."""
    if not date_input:
        return "", ""

    date_str = str(date_input)

    iso_match = re.match(r'(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})', date_str)
    if iso_match:
        return iso_match.group(1), iso_match.group(2)

    date_match = re.match(r'(\d{4}-\d{2}-\d{2})', date_str)
    if date_match:
        return date_match.group(1), ""

    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(date_str[:26], fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S") if "%H" in fmt else ""
        except (ValueError, TypeError):
            continue

    return "", ""

def parse_date_for_sort(date_str, time_str=""):
    """Convert date_str and time_str to a sortable datetime string."""
    if not date_str:
        return "0000-00-00T00:00:00"

    date_part = date_str[:10]
    time_part = time_str[:8] if time_str else "00:00:00"
    return f"{date_part}T{time_part}"