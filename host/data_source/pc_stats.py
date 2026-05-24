"""PC hardware stats — CPU, RAM, disk, battery."""

import sys

import psutil

_SKIP_FSTYPES = {"", "squashfs", "tmpfs", "devtmpfs"}


def _total_disk_pct() -> float:
    """Aggregate used/total across all physical partitions, deduplicated by device."""
    total = used = 0
    seen: set = set()
    for part in psutil.disk_partitions(all=False):
        if part.fstype in _SKIP_FSTYPES:
            continue
        if sys.platform == "win32" and "cdrom" in part.opts:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        key = (usage.total, part.device)
        if key in seen:
            continue
        seen.add(key)
        total += usage.total
        used  += usage.used
    return round(used / total * 100, 1) if total else 0.0


def read() -> dict:
    bat = psutil.sensors_battery()
    return {
        "cpu":  round(psutil.cpu_percent(interval=None), 1),
        "ram":  round(psutil.virtual_memory().percent, 1),
        "disk": _total_disk_pct(),
        "bat":  round(bat.percent) if bat else None,
    }
