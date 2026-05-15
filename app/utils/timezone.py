from datetime import datetime
from zoneinfo import ZoneInfo

LAGOS_TZ = ZoneInfo("Africa/Lagos")


def now_lagos() -> datetime:
    """Return timezone-aware current time in Africa/Lagos."""
    return datetime.now(LAGOS_TZ)
