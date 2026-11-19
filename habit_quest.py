#!/usr/bin/env python3
"""Habit Quest - a tiny terminal RPG habit tracker.

Complete real-life quests, earn XP, keep streaks alive and level up your hero.
Run ``python3 habit_quest.py --help`` for the full command list.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

STATE_VERSION = 2
DEFAULT_STATE_FILE = Path(
    os.environ.get("HABIT_QUEST_STATE", "~/.habit_quest.json")
).expanduser()

LEVEL_STEP = 100
MAX_LOG_ENTRIES = 800
MAX_HABIT_NAME = 60
MAX_HERO_NAME = 32
MAX_XP = 500
STREAK_BONUS_CAP = 10

# Highest rank first; the first threshold that the level reaches wins.
RANKS = (
    (30, "Legend"),
    (20, "Champion"),
    (15, "Knight"),
    (10, "Squire"),
    (5, "Apprentice"),
    (1, "Novice"),
)

ACHIEVEMENTS = (
    {
        "id": "first_quest",
        "name": "First Blood",
        "desc": "Complete your very first quest.",
        "icon": "sword",
    },
    {
        "id": "streak_3",
        "name": "Kindled",
        "desc": "Hold a 3-day streak.",
        "icon": "flame",
    },
    {
        "id": "streak_7",
        "name": "Week of Fire",
        "desc": "Hold a 7-day streak.",
        "icon": "flame",
    },
    {
        "id": "streak_30",
        "name": "Eternal Flame",
        "desc": "Hold a 30-day streak.",
        "icon": "flame",
    },
    {
        "id": "level_5",
        "name": "Apprentice",
        "desc": "Reach hero level 5.",
        "icon": "shield",
    },
    {
        "id": "level_10",
        "name": "Squire",
        "desc": "Reach hero level 10.",
        "icon": "crown",
    },
    {
        "id": "quests_10",
        "name": "Quest Runner",
        "desc": "Clear 10 quests in total.",
        "icon": "scroll",
    },
    {
        "id": "quests_50",
        "name": "Dungeon Delver",
        "desc": "Clear 50 quests in total.",
        "icon": "star",
    },
    {
        "id": "boss_slayer",
        "name": "Boss Slayer",
        "desc": "Clear every quest in a single day.",
        "icon": "skull",
    },
)

BOSS_NAMES = (
    "Lord Procrastinus",
    "The Snooze Wraith",
    "Duke Dilly-Dally",
    "Mistress Maybe-Later",
)


class AlreadyDoneToday(Exception):
    """Raised when a habit was already completed on the given day."""


@dataclass
class CompletionResult:
    """Everything the CLI and the web UI need to celebrate a completion."""

    habit: str
    base_xp: int
    streak_bonus: int
    xp_awarded: int
    streak: int
    leveled_up: bool
    levels_gained: int
    level: int
    xp: int
    xp_next: int
    new_achievements: list[dict]

    def to_dict(self) -> dict:
        return {
            "habit": self.habit,
            "base_xp": self.base_xp,
            "streak_bonus": self.streak_bonus,
            "xp_awarded": self.xp_awarded,
            "streak": self.streak,
            "leveled_up": self.leveled_up,
            "levels_gained": self.levels_gained,
            "level": self.level,
            "xp": self.xp,
            "xp_next": self.xp_next,
            "new_achievements": [dict(item) for item in self.new_achievements],
        }


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def default_state_file() -> Path:
    """Return the state path, honouring the HABIT_QUEST_STATE override."""

    return Path(
        os.environ.get("HABIT_QUEST_STATE", "~/.habit_quest.json")
    ).expanduser()


def xp_for_next_level(level: int) -> int:
    return max(1, level) * LEVEL_STEP


def rank_for_level(level: int) -> str:
    for threshold, rank in RANKS:
        if level >= threshold:
            return rank
    return RANKS[-1][1]


def next_rank_info(state: dict) -> dict | None:
    """Return the next rank and the XP still needed to reach its level."""

    for threshold, rank in sorted(RANKS, key=lambda item: item[0]):
        if threshold <= state["level"]:
            continue
        needed = xp_for_next_level(state["level"]) - state["xp"]
        for level in range(state["level"] + 1, threshold):
            needed += xp_for_next_level(level)
        return {"name": rank, "level": threshold, "xp_needed": max(0, needed)}
    return None


def new_state() -> dict:
    return {
        "version": STATE_VERSION,
        "hero_name": "Wanderer",
        "xp": 0,
        "level": 1,
        "habits": {},
        "log": [],
        "stats": {
            "completions": 0,
            "xp_earned": 0,
            "best_streak": 0,
        },
    }


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_state(raw: dict) -> dict:
    """Turn any older or partially broken save file into a valid state."""

    state = new_state()
    if not isinstance(raw, dict):
        return state

    hero = str(raw.get("hero_name") or "Wanderer").strip()[:MAX_HERO_NAME]
    state["hero_name"] = hero or "Wanderer"
    state["level"] = max(1, _as_int(raw.get("level"), 1))
    state["xp"] = max(0, _as_int(raw.get("xp"), 0))

    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    state["stats"] = {
        "completions": max(0, _as_int(stats.get("completions"), 0)),
        "xp_earned": max(0, _as_int(stats.get("xp_earned"), 0)),
        "best_streak": max(0, _as_int(stats.get("best_streak"), 0)),
    }

    habits = raw.get("habits") if isinstance(raw.get("habits"), dict) else {}
    for name, info in habits.items():
        if not isinstance(info, dict):
            continue
        clean_name = str(name).strip()[:MAX_HABIT_NAME]
        if not clean_name:
            continue
        streak = max(0, _as_int(info.get("streak"), 0))
        state["habits"][clean_name] = {
            "xp": min(MAX_XP, max(1, _as_int(info.get("xp"), 20))),
            "streak": streak,
            "best_streak": max(streak, _as_int(info.get("best_streak"), streak)),
            "last_done": info.get("last_done"),
            "completions": max(0, _as_int(info.get("completions"), 0)),
            "created": str(info.get("created") or date.today().isoformat()),
        }
        state["stats"]["best_streak"] = max(
            state["stats"]["best_streak"], state["habits"][clean_name]["best_streak"]
        )

    log = raw.get("log") if isinstance(raw.get("log"), list) else []
    state["log"] = [
        entry
        for entry in log
        if isinstance(entry, dict) and entry.get("type") == "complete"
    ][-MAX_LOG_ENTRIES:]

    # Old saves stored a raw XP total that may exceed the current level cost.
    while state["xp"] >= xp_for_next_level(state["level"]):
        state["xp"] -= xp_for_next_level(state["level"])
        state["level"] += 1
    return state


def load_state(path: Path | str | None = None) -> dict:
    target = Path(path).expanduser() if path else default_state_file()
    if not target.exists():
        return new_state()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return new_state()
    return normalize_state(raw)


def save_state(state: dict, path: Path | str | None = None) -> None:
    target = Path(path).expanduser() if path else default_state_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, ensure_ascii=False)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)


# ---------------------------------------------------------------------------
# Game rules
# ---------------------------------------------------------------------------


def streak_bonus(streak: int) -> int:
    """Every streak day adds a little extra XP, capped at ten days."""

    return 2 * min(max(streak, 0), STREAK_BONUS_CAP)


def add_habit(state: dict, name: str, xp: int = 20) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Habit name cannot be empty.")
    if len(name) > MAX_HABIT_NAME:
        raise ValueError(f"Habit name must be at most {MAX_HABIT_NAME} characters.")
    if name in state["habits"]:
        raise ValueError(f"Habit already exists: {name}")
    if not 1 <= xp <= MAX_XP:
        raise ValueError(f"XP must be between 1 and {MAX_XP}.")
    state["habits"][name] = {
        "xp": xp,
        "streak": 0,
        "best_streak": 0,
        "last_done": None,
        "completions": 0,
        "created": date.today().isoformat(),
    }
    return state


def remove_habit(state: dict, name: str) -> dict:
    if name not in state["habits"]:
        raise KeyError(f"Habit not found: {name}")
    del state["habits"][name]
    return state


def rename_hero(state: dict, name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Hero name cannot be empty.")
    state["hero_name"] = name[:MAX_HERO_NAME]
    return state


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def current_streak(info: dict, today: date | None = None) -> int:
    """A streak is only alive if the habit was cleared today or yesterday."""

    today = today or date.today()
    last = _parse_date(info.get("last_done"))
    if last is None or (today - last) > timedelta(days=1):
        return 0
    return info["streak"]


def complete_habit(
    state: dict,
    name: str,
    today: date | None = None,
    now: datetime | None = None,
) -> CompletionResult:
    """Complete a habit for ``today`` and return a celebration payload.

    Streaks only advance once per calendar day. Completing the same habit
    twice on one day raises :class:`AlreadyDoneToday`.
    """

    if name not in state["habits"]:
        raise KeyError(f"Habit not found: {name}")

    today = today or date.today()
    now = now or datetime.now()
    today_s = today.isoformat()
    habit = state["habits"][name]

    if habit.get("last_done") == today_s:
        raise AlreadyDoneToday(f"'{name}' is already cleared today.")

    before_achievements = {
        item["id"] for item in unlocked_achievements(state)
    }

    previous = {
        "xp": habit["xp"],
        "streak": habit["streak"],
        "best_streak": habit["best_streak"],
        "last_done": habit["last_done"],
        "completions": habit["completions"],
    }
    hero_xp_before = state["xp"]
    level_before = state["level"]

    last_done = _parse_date(habit.get("last_done"))
    if last_done == today - timedelta(days=1):
        streak = habit["streak"] + 1
    else:
        streak = 1

    bonus = streak_bonus(streak)
    awarded = habit["xp"] + bonus

    habit["streak"] = streak
    habit["best_streak"] = max(habit["best_streak"], streak)
    habit["last_done"] = today_s
    habit["completions"] += 1

    state["xp"] += awarded
    state["stats"]["completions"] += 1
    state["stats"]["xp_earned"] += awarded
    state["stats"]["best_streak"] = max(
        state["stats"]["best_streak"], habit["best_streak"]
    )

    levels_gained = 0
    while state["xp"] >= xp_for_next_level(state["level"]):
        state["xp"] -= xp_for_next_level(state["level"])
        state["level"] += 1
        levels_gained += 1

    state["log"].append(
        {
            "type": "complete",
            "at": now.replace(microsecond=0).isoformat(),
            "date": today_s,
            "habit": name,
            "xp": awarded,
            "base": habit["xp"],
            "bonus": bonus,
            "streak": streak,
            "level_before": level_before,
            "xp_before": hero_xp_before,
            "prev": previous,
        }
    )
    state["log"] = state["log"][-MAX_LOG_ENTRIES:]

    new_achievements = [
        item
        for item in unlocked_achievements(state)
        if item["id"] not in before_achievements
    ]

    return CompletionResult(
        habit=name,
        base_xp=habit["xp"],
        streak_bonus=bonus,
        xp_awarded=awarded,
        streak=streak,
        leveled_up=levels_gained > 0,
        levels_gained=levels_gained,
        level=state["level"],
        xp=state["xp"],
        xp_next=xp_for_next_level(state["level"]),
        new_achievements=new_achievements,
    )


def undo_last(state: dict) -> dict:
    """Revert the most recent completion and return its log entry."""

    for index in range(len(state["log"]) - 1, -1, -1):
        entry = state["log"][index]
        if entry.get("type") != "complete":
            continue
        name = entry.get("habit")
        habit = state["habits"].get(name)
        if habit is None:
            raise ValueError(f"Cannot undo '{name}': the habit was removed.")
        previous = entry.get("prev") or {}
        if isinstance(previous.get("completions"), int):
            habit["completions"] = previous["completions"]
        else:
            habit["completions"] = max(0, habit["completions"] - 1)
        if "streak" in previous:
            habit["streak"] = _as_int(previous.get("streak"), habit["streak"])
        if "best_streak" in previous:
            habit["best_streak"] = _as_int(
                previous.get("best_streak"), habit["best_streak"]
            )
        if "last_done" in previous:
            habit["last_done"] = previous.get("last_done")

        if "level_before" in entry:
            state["level"] = max(1, _as_int(entry.get("level_before"), 1))
        if "xp_before" in entry:
            state["xp"] = max(0, _as_int(entry.get("xp_before"), 0))

        state["stats"]["completions"] = max(
            0, state["stats"]["completions"] - 1
        )
        state["stats"]["xp_earned"] = max(
            0, state["stats"]["xp_earned"] - _as_int(entry.get("xp"), 0)
        )
        state["stats"]["best_streak"] = max(
            (info["best_streak"] for info in state["habits"].values()), default=0
        )
        state["log"].pop(index)
        return entry
    raise ValueError("There is nothing to undo.")


# ---------------------------------------------------------------------------
# Achievements, activity and dashboard
# ---------------------------------------------------------------------------


def _boss_slayer(state: dict) -> bool:
    habits = set(state["habits"])
    if not habits:
        return False
    by_day: dict[str, set[str]] = {}
    for entry in state["log"]:
        day = entry.get("date")
        habit = entry.get("habit")
        if day and habit in habits:
            by_day.setdefault(day, set()).add(habit)
    return any(completed >= habits for completed in by_day.values())


def unlocked_achievements(state: dict) -> list[dict]:
    """Return achievement definitions decorated with an ``unlocked`` flag."""

    stats = state.get("stats", {})
    completions = stats.get("completions", 0)
    best_streak = stats.get("best_streak", 0)
    level = state.get("level", 1)
    conditions = {
        "first_quest": completions >= 1,
        "streak_3": best_streak >= 3,
        "streak_7": best_streak >= 7,
        "streak_30": best_streak >= 30,
        "level_5": level >= 5,
        "level_10": level >= 10,
        "quests_10": completions >= 10,
        "quests_50": completions >= 50,
        "boss_slayer": _boss_slayer(state),
    }
    return [
        {**definition, "unlocked": bool(conditions.get(definition["id"]))}
        for definition in ACHIEVEMENTS
    ]


def recent_activity(state: dict, limit: int = 8) -> list[dict]:
    entries = []
    for entry in reversed(state["log"]):
        if entry.get("type") != "complete":
            continue
        entries.append(
            {
                "at": entry.get("at"),
                "date": entry.get("date"),
                "habit": entry.get("habit"),
                "xp": entry.get("xp", 0),
                "streak": entry.get("streak", 0),
            }
        )
        if len(entries) >= limit:
            break
    return entries


def heatmap_days(
    state: dict, today: date | None = None, weeks: int = 12
) -> list[dict]:
    """Return ``weeks * 7`` days, Monday-aligned, ending with this week."""

    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(weeks=weeks - 1)
    counts: dict[str, int] = {}
    for entry in state["log"]:
        day = entry.get("date")
        if day:
            counts[day] = counts.get(day, 0) + 1

    days = []
    for offset in range(weeks * 7):
        current = start + timedelta(days=offset)
        count = counts.get(current.isoformat(), 0)
        level = 0 if count == 0 else min(4, 1 + (count - 1) // 2)
        days.append(
            {
                "date": current.isoformat(),
                "count": count,
                "level": level,
                "future": current > today,
            }
        )
    return days


def active_days(state: dict) -> int:
    return len({entry.get("date") for entry in state["log"] if entry.get("date")})


def build_dashboard(state: dict, today: date | None = None) -> dict:
    """Shape state into the JSON payload used by the web interface."""

    today = today or date.today()
    today_s = today.isoformat()
    achievements = unlocked_achievements(state)

    habits = []
    remaining = []
    for name, info in state["habits"].items():
        done_today = info.get("last_done") == today_s
        habits.append(
            {
                "name": name,
                "xp": info["xp"],
                "streak": current_streak(info, today),
                "best_streak": info["best_streak"],
                "completions": info["completions"],
                "last_done": info.get("last_done"),
                "done_today": done_today,
            }
        )
        if not done_today:
            remaining.append(name)

    # Open quests first so the next action is always at the top.
    habits.sort(key=lambda item: (item["done_today"], item["name"]))

    completed_today = sum(1 for item in habits if item["done_today"])
    boss_index = today.toordinal() % len(BOSS_NAMES)
    return {
        "version": state["version"],
        "today": today_s,
        "hero": {
            "name": state["hero_name"],
            "level": state["level"],
            "rank": rank_for_level(state["level"]),
            "xp": state["xp"],
            "xp_next": xp_for_next_level(state["level"]),
            "xp_pct": round(
                100 * state["xp"] / xp_for_next_level(state["level"]), 1
            ),
            "xp_earned": state["stats"]["xp_earned"],
            "next_rank": next_rank_info(state),
        },
        "stats": {
            "completions": state["stats"]["completions"],
            "best_streak": state["stats"]["best_streak"],
            "active_days": active_days(state),
            "quests": len(habits),
            "completed_today": completed_today,
        },
        "habits": habits,
        "achievements": achievements,
        "next_relic": next(
            (item for item in achievements if not item["unlocked"]), None
        ),
        "recent": recent_activity(state, limit=7),
        "heatmap": heatmap_days(state, today=today),
        "boss": {
            "name": BOSS_NAMES[boss_index],
            "hp": len(remaining),
            "max": len(habits),
            "remaining": remaining,
            "defeated": bool(habits) and not remaining,
        },
    }


# ---------------------------------------------------------------------------
# Demo seed
# ---------------------------------------------------------------------------


def seed_demo(state: dict, today: date | None = None) -> dict:
    """Fill ``state`` with four weeks of believable adventuring history."""

    import random

    today = today or date.today()
    fresh = new_state()
    fresh["hero_name"] = "Aria the Emberbound"
    state.clear()
    state.update(fresh)

    quests = (
        ("Read 20 pages", 25),
        ("Morning run", 30),
        ("Meditate 10 min", 20),
        ("Practice guitar", 25),
        ("Drink water", 10),
    )
    for name, xp in quests:
        add_habit(state, name, xp)

    rng = random.Random(20261119)
    for offset in range(27, -1, -1):
        day = today - timedelta(days=offset)
        chosen = ["Read 20 pages"]
        if rng.random() < 0.85:
            chosen.append("Drink water")
        if rng.random() < 0.7:
            chosen.append("Meditate 10 min")
        if day.weekday() in (0, 2, 4):
            chosen.append("Morning run")
        if rng.random() < 0.45:
            chosen.append("Practice guitar")
        if offset == 0:
            # Leave two quests open so the demo dashboard has work to do.
            chosen = ["Read 20 pages", "Meditate 10 min", "Drink water"]
        for name in chosen:
            now = datetime.combine(day, time(7 + rng.randrange(0, 12), 0))
            complete_habit(state, name, today=day, now=now)

    # Those four visible weeks are only the latest chapter: the hero has older
    # adventures behind them, so start the demo on a nearly-full level bar.
    state["level"] = 9
    state["xp"] = 640
    return state


# ---------------------------------------------------------------------------
# CLI rendering
# ---------------------------------------------------------------------------


def _bar(value: int, total: int, width: int = 18) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = max(0, min(width, round(width * value / total)))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def format_status(state: dict, today: date | None = None) -> str:
    today = today or date.today()
    today_s = today.isoformat()
    rank = rank_for_level(state["level"])
    lines = [
        f"HABIT QUEST  |  {state['hero_name']}",
        f"Level {state['level']} {rank}   "
        f"{state['xp']} / {xp_for_next_level(state['level'])} XP  "
        f"{_bar(state['xp'], xp_for_next_level(state['level']))}",
        "",
    ]

    habits = list(state["habits"].items())
    done = sum(1 for _, info in habits if info.get("last_done") == today_s)
    if habits:
        lines.append(
            f"{len(habits)} quests  |  {done} cleared today  |  "
            f"boss HP {len(habits) - done}/{len(habits)}"
        )
        lines.append("")
        lines.append("TODAY'S QUESTS")
        for name, info in habits:
            if info.get("last_done") == today_s:
                mark = "[x]"
                extra = "done"
            else:
                mark = "[ ]"
                extra = "open"
            lines.append(
                f"  {mark} {name[:30]:<30} +{info['xp']:>3} XP  "
                f"streak {current_streak(info, today):>3}  "
                f"best {info['best_streak']:>3}  {extra}"
            )
    else:
        lines.append('No quests yet. Add one with: habit_quest.py add "Read 20 pages"')

    relics = unlocked_achievements(state)
    unlocked = sum(1 for item in relics if item["unlocked"])
    lines += [
        "",
        f"RELICS {unlocked}/{len(relics)}  |  "
        f"cleared {state['stats']['completions']}  |  "
        f"best streak {state['stats']['best_streak']}  |  "
        f"days adventured {active_days(state)}",
    ]
    for item in relics:
        if item["unlocked"]:
            lines.append(f"  [{item['name']}] {item['desc']}")
    return "\n".join(lines)


def format_achievements(state: dict) -> str:
    lines = ["RELICS OF THE EMBERBOUND"]
    for item in unlocked_achievements(state):
        mark = "x" if item["unlocked"] else " "
        lines.append(f"  [{mark}] {item['name']:<14} {item['desc']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="habit_quest.py",
        description="Habit Quest - a terminal RPG habit tracker.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=None,
        help="state file to use (default: ~/.habit_quest.json, or $HABIT_QUEST_STATE)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add a new habit quest")
    p_add.add_argument("name")
    p_add.add_argument("--xp", type=int, default=20, help="XP reward (1-500)")

    p_done = sub.add_parser("done", help="Complete a habit quest")
    p_done.add_argument("name")

    p_remove = sub.add_parser("remove", help="Remove a habit quest")
    p_remove.add_argument("name")

    sub.add_parser("status", help="Show the hero sheet and today's quests")
    sub.add_parser("achievements", help="List all relics and their progress")

    p_log = sub.add_parser("log", help="Show recent completions")
    p_log.add_argument("--limit", type=int, default=10)

    sub.add_parser("undo", help="Undo the most recent completion")
    p_reset = sub.add_parser("reset", help="Erase all progress")
    p_reset.add_argument(
        "--yes", action="store_true", help="confirm erasing every quest and relic"
    )

    p_rename = sub.add_parser("rename", help="Rename your hero")
    p_rename.add_argument("name")

    p_export = sub.add_parser("export", help="Write a copy of the save file")
    p_export.add_argument("path", type=Path)

    p_import = sub.add_parser("import", help="Load a save file")
    p_import.add_argument("path", type=Path)

    p_demo = sub.add_parser("demo", help="Fill the save with a demo adventure")
    p_demo.add_argument(
        "--yes", action="store_true", help="replace existing progress without asking"
    )

    p_serve = sub.add_parser("serve", help="Open the web dungeon dashboard")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--open", action="store_true", help="open a browser tab")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    state_path = (args.state or default_state_file()).expanduser()

    if args.cmd == "serve":
        from quest_web import run_server

        run_server(
            state_path=state_path,
            host=args.host,
            port=args.port,
            open_browser=args.open,
        )
        return 0

    state = load_state(state_path)

    try:
        if args.cmd == "add":
            add_habit(state, args.name, args.xp)
            save_state(state, state_path)
            print(f"Added quest: {args.name} (+{args.xp} XP)")
        elif args.cmd == "done":
            result = complete_habit(state, args.name)
            save_state(state, state_path)
            message = (
                f"Cleared '{result.habit}'! +{result.xp_awarded} XP "
                f"(streak {result.streak}, +{result.streak_bonus} bonus)  "
                f"Level {result.level} {result.xp}/{result.xp_next}"
            )
            if result.leveled_up:
                message += f"  LEVEL UP x{result.levels_gained}!"
            print(message)
            for item in result.new_achievements:
                print(f"  New relic unlocked: {item['name']} - {item['desc']}")
        elif args.cmd == "remove":
            remove_habit(state, args.name)
            save_state(state, state_path)
            print(f"Removed quest: {args.name}")
        elif args.cmd == "status":
            print(format_status(state))
        elif args.cmd == "achievements":
            print(format_achievements(state))
        elif args.cmd == "log":
            entries = recent_activity(state, limit=max(1, args.limit))
            if not entries:
                print("No completions logged yet.")
            for entry in entries:
                print(
                    f"{entry['date']}  {entry['habit']:<28} +{entry['xp']:>3} XP  "
                    f"streak {entry['streak']}"
                )
        elif args.cmd == "undo":
            entry = undo_last(state)
            save_state(state, state_path)
            print(
                f"Undid '{entry.get('habit')}' from {entry.get('date')} "
                f"(-{entry.get('xp', 0)} XP)."
            )
        elif args.cmd == "reset":
            if not args.yes:
                raise ValueError(
                    "This erases all progress. Re-run with: reset --yes"
                )
            state = new_state()
            save_state(state, state_path)
            print("The dungeon has been wiped clean. A new adventure begins.")
        elif args.cmd == "rename":
            rename_hero(state, args.name)
            save_state(state, state_path)
            print(f"Hero renamed to {state['hero_name']}.")
        elif args.cmd == "export":
            save_state(state, args.path)
            print(f"Saved a copy to {args.path}")
        elif args.cmd == "import":
            if not args.path.exists():
                raise FileNotFoundError(f"No such file: {args.path}")
            imported = normalize_state(
                json.loads(args.path.read_text(encoding="utf-8"))
            )
            save_state(imported, state_path)
            print(f"Imported adventure from {args.path}")
        elif args.cmd == "demo":
            if args.yes or not state["habits"]:
                seed_demo(state)
                save_state(state, state_path)
                print(
                    "The demo adventure is ready. "
                    f"Run: python3 habit_quest.py --state {state_path} serve"
                )
            else:
                raise ValueError(
                    "This save already has progress. Re-run with --yes to replace it."
                )
    except (KeyError, ValueError, AlreadyDoneToday, FileNotFoundError) as error:
        message = error.args[0] if error.args else str(error)
        print(f"Error: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
