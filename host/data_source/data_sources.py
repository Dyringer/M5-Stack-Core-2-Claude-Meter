"""Build the flat data pool {source_key: value} from API payload and PC stats."""

import data_source.pc_stats as pc_stats


def _fmt_reset(minutes: int) -> str:
    if minutes <= 0:
        return "now"
    if minutes < 60:
        return "{}m".format(minutes)
    hours, mins = divmod(minutes, 60)
    return "{}h{:02d}m".format(hours, mins)


def collect(api_payload: dict) -> dict:
    """Return flat {source_key: value} pool for the current cycle."""
    pc  = pc_stats.read()
    bat = pc["bat"]

    pool = {
        "pc.cpu.usage.int":  pc["cpu"],
        "pc.cpu.usage.str":  "{}%".format(pc["cpu"]),
        "pc.ram.usage.int":  pc["ram"],
        "pc.ram.usage.str":  "{}%".format(pc["ram"]),
        "pc.disk.usage.int": pc["disk"],
        "pc.disk.usage.str": "{}%".format(pc["disk"]),
        "pc.bat.level.int":  bat if bat is not None else 0,
        "pc.bat.level.str":  "{}%".format(bat) if bat is not None else "--",
    }

    for window in ("5h", "7d"):
        pct   = api_payload.get(f"{window}_utilization_pct", 0)
        reset = api_payload.get(f"{window}_reset_minutes",   0)
        pool[f"claude.{window}.usage.int"] = pct
        pool[f"claude.{window}.usage.str"] = "{}%".format(pct)
        pool[f"claude.{window}.reset.int"] = reset
        pool[f"claude.{window}.reset.str"] = "rst {}".format(_fmt_reset(reset))

    return pool
