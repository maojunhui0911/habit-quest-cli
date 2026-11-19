#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

DEFAULT_STATE_FILE = Path.home() / ".habit_quest.json"


def load_state(path: Path = DEFAULT_STATE_FILE) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"xp": 0, "level": 1, "habits": {}}


def save_state(state: dict, path: Path = DEFAULT_STATE_FILE) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def xp_for_next_level(level: int) -> int:
    return level * 100


def add_habit(state: dict, name: str, xp: int = 20) -> dict:
    state["habits"][name] = {"xp": xp, "streak": 0}
    return state


def complete_habit(state: dict, name: str) -> tuple[dict, bool]:
    if name not in state["habits"]:
        raise KeyError(f"Habit not found: {name}")
    habit = state["habits"][name]
    habit["streak"] += 1
    state["xp"] += habit["xp"]
    leveled_up = False
    while state["xp"] >= xp_for_next_level(state["level"]):
        state["xp"] -= xp_for_next_level(state["level"])
        state["level"] += 1
        leveled_up = True
    return state, leveled_up


def main() -> None:
    parser = argparse.ArgumentParser(description="Habit Quest CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add a new habit")
    p_add.add_argument("name")
    p_add.add_argument("--xp", type=int, default=20)

    p_done = sub.add_parser("done", help="Complete a habit")
    p_done.add_argument("name")

    sub.add_parser("status", help="Show hero status")

    args = parser.parse_args()
    state = load_state()

    if args.cmd == "add":
        add_habit(state, args.name, args.xp)
        save_state(state)
        print(f"Added habit: {args.name} (+{args.xp} XP)")
    elif args.cmd == "done":
        state, leveled_up = complete_habit(state, args.name)
        save_state(state)
        msg = f"Completed '{args.name}'! Level {state['level']} ({state['xp']}/{xp_for_next_level(state['level'])} XP)"
        if leveled_up:
            msg += " 🎉 LEVEL UP!"
        print(msg)
    elif args.cmd == "status":
        print(f"Hero Level: {state['level']} | XP: {state['xp']}/{xp_for_next_level(state['level'])}")
        for name, info in state["habits"].items():
            print(f"  - {name}: +{info['xp']} XP (streak: {info['streak']})")


if __name__ == "__main__":
    main()
