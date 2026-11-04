"""Hardware & Power environment integration: Battery state and Solar / Day-Night detection."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("lumi.hardware")


def get_power_status() -> Tuple[bool, Optional[int]]:
    """Return (on_battery: bool, percentage: Optional[int]). Safe on any Linux system."""
    sys_power = Path("/sys/class/power_supply")
    if not sys_power.exists():
        return False, None

    on_battery = False
    percentages = []

    try:
        for ps in sys_power.iterdir():
            ps_type = ps / "type"
            if not ps_type.exists():
                continue
            type_str = ps_type.read_text().strip()

            if type_str == "Battery":
                status_file = ps / "status"
                capacity_file = ps / "capacity"

                if status_file.exists():
                    st = status_file.read_text().strip().lower()
                    if st in ("discharging", "not charging"):
                        on_battery = True

                if capacity_file.exists():
                    try:
                        percentages.append(int(capacity_file.read_text().strip()))
                    except ValueError:
                        pass
            elif type_str == "Mains":
                online_file = ps / "online"
                if online_file.exists() and online_file.read_text().strip() == "0":
                    on_battery = True
    except Exception as exc:
        logger.debug("Failed reading power supply state: %s", exc)

    avg_pct = int(sum(percentages) / len(percentages)) if percentages else None
    return on_battery, avg_pct


def is_daytime(day_start_hour: int = 6, night_start_hour: int = 18) -> bool:
    """Determine if the current system time is during daytime hours."""
    now = datetime.datetime.now().time()
    day_start = datetime.time(day_start_hour, 0)
    night_start = datetime.time(night_start_hour, 0)

    if day_start <= night_start:
        return day_start <= now < night_start
    return now >= day_start or now < night_start
