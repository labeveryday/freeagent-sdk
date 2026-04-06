"""System information tool."""

import os
import platform
import shutil
from ..tool import tool


@tool
def system_info(check: str = "all") -> dict:
    """Get system information: disk, memory, cpu, or all.

    check: What to check — "disk", "cpu", "os", or "all"
    """
    result = {}

    if check in ("disk", "all"):
        usage = shutil.disk_usage("/")
        result["disk_total_gb"] = round(usage.total / (1024**3), 2)
        result["disk_free_gb"] = round(usage.free / (1024**3), 2)
        result["disk_used_percent"] = round(
            (usage.used / usage.total) * 100, 1
        )

    if check in ("cpu", "all"):
        result["cpu_cores"] = os.cpu_count()

    if check in ("os", "all"):
        result["os_name"] = platform.system()
        result["os_version"] = platform.release()
        result["hostname"] = platform.node()

    return result
