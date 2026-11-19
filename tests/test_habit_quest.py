import contextlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

import quest_web
from habit_quest import (
    AlreadyDoneToday,
    add_habit,
    build_dashboard,
    complete_habit,
    current_streak,
    heatmap_days,
    load_state,
    main,
    new_state,
    normalize_state,
    remove_habit,
    rename_hero,
    save_state,
    seed_demo,
    undo_last,
    unlocked_achievements,
    xp_for_next_level,
)


class TestHabitQuest(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 19)
        self.state = new_state()

    def add(self, name="Exercise", xp=20):
        add_habit(self.state, name, xp)

    def complete(self, name="Exercise", day=None):
        day = day or self.today
        return complete_habit(
            self.state, name, today=day, now=datetime.combine(day, time(9, 0))
        )

    def test_add_and_complete_levels_up(self):
        add_habit(self.state, "Exercise", xp=120)
        result = complete_habit(self.state, "Exercise", today=self.today)

        self.assertTrue(result.leveled_up)
        self.assertEqual(result.levels_gained, 1)
        self.assertEqual(self.state["level"], 2)
        # 120 base + 2 first-day streak bonus, minus the 100 XP level cost.
        self.assertEqual(result.xp_awarded, 122)
        self.assertEqual(self.state["xp"], 22)
        self.assertEqual(self.state["habits"]["Exercise"]["streak"], 1)
        self.assertEqual(len(self.state["log"]), 1)

    def test_add_habit_validation(self):
        add_habit(self.state, "Read")
        with self.assertRaises(ValueError):
            add_habit(self.state, "Read")
        with self.assertRaises(ValueError):
            add_habit(self.state, "   ")
        with self.assertRaises(ValueError):
            add_habit(self.state, "Run", xp=0)
        with self.assertRaises(ValueError):
            add_habit(self.state, "Run", xp=999)

    def test_missing_habit_raises(self):
        with self.assertRaises(KeyError):
            complete_habit(self.state, "Nope")

    def test_same_day_completion_is_rejected(self):
        self.add()
        self.complete()
        with self.assertRaises(AlreadyDoneToday):
            self.complete()

    def test_streaks_grow_and_reset(self):
        self.add()
        self.complete(day=self.today)
        second = self.complete(day=self.today + timedelta(days=1))
        self.assertEqual(second.streak, 2)
        self.assertEqual(second.streak_bonus, 4)
        self.assertEqual(second.xp_awarded, 24)

        # Skip a day: the streak cools down and starts again at one.
        third = self.complete(day=self.today + timedelta(days=4))
        self.assertEqual(third.streak, 1)
        self.assertEqual(third.streak_bonus, 2)

    def test_current_streak_cools_off_after_a_gap(self):
        self.add()
        self.complete(day=self.today)
        self.assertEqual(current_streak(self.state["habits"]["Exercise"], self.today), 1)
        self.assertEqual(
            current_streak(self.state["habits"]["Exercise"], self.today + timedelta(days=2)),
            0,
        )

    def test_streak_bonus_is_capped(self):
        self.add()
        day = self.today - timedelta(days=20)
        for offset in range(20):
            result = self.complete(day=day + timedelta(days=offset))
        self.assertEqual(result.streak, 20)
        self.assertEqual(result.streak_bonus, 20)  # 2 XP per day, capped at 10 days

    def test_undo_restores_hero_and_habit(self):
        self.add(xp=120)
        self.complete()
        after_first = {
            "level": self.state["level"],
            "xp": self.state["xp"],
            "streak": self.state["habits"]["Exercise"]["streak"],
            "last_done": self.state["habits"]["Exercise"]["last_done"],
        }
        self.complete(day=self.today + timedelta(days=1))

        entry = undo_last(self.state)
        self.assertEqual(entry["habit"], "Exercise")
        self.assertEqual(self.state["level"], after_first["level"])
        self.assertEqual(self.state["xp"], after_first["xp"])
        self.assertEqual(self.state["habits"]["Exercise"]["streak"], 1)
        self.assertEqual(self.state["habits"]["Exercise"]["last_done"], self.today.isoformat())
        self.assertEqual(len(self.state["log"]), 1)
        self.assertEqual(self.state["stats"]["completions"], 1)

        undo_last(self.state)
        self.assertEqual(self.state["stats"]["completions"], 0)
        with self.assertRaises(ValueError):
            undo_last(self.state)

    def test_undo_refuses_when_habit_was_removed(self):
        self.add()
        self.complete()
        remove_habit(self.state, "Exercise")
        with self.assertRaises(ValueError):
            undo_last(self.state)

    def test_achievements(self):
        self.add("Read")
        self.add("Run")
        unlocked = {item["id"] for item in unlocked_achievements(self.state) if item["unlocked"]}
        self.assertNotIn("first_quest", unlocked)

        day = self.today - timedelta(days=7)
        for offset in range(7):
            complete_habit(self.state, "Read", today=day + timedelta(days=offset))
        self.complete("Run", day=self.today - timedelta(days=7))

        unlocked = {item["id"] for item in unlocked_achievements(self.state) if item["unlocked"]}
        for achievement_id in ("first_quest", "streak_3", "streak_7"):
            self.assertIn(achievement_id, unlocked)
        self.assertNotIn("streak_30", unlocked)

        # Every quest cleared on the same day unlocks Boss Slayer.
        self.complete("Read")
        self.complete("Run")
        unlocked = {item["id"] for item in unlocked_achievements(self.state) if item["unlocked"]}
        self.assertIn("boss_slayer", unlocked)
        self.assertIn("quests_10", unlocked)

    def test_remove_and_rename(self):
        self.add()
        remove_habit(self.state, "Exercise")
        self.assertNotIn("Exercise", self.state["habits"])
        with self.assertRaises(KeyError):
            remove_habit(self.state, "Exercise")

        rename_hero(self.state, "  Aria  ")
        self.assertEqual(self.state["hero_name"], "Aria")
        with self.assertRaises(ValueError):
            rename_hero(self.state, "  ")

    def test_normalize_migrates_v1_state(self):
        old = {
            "xp": 250,
            "level": 1,
            "habits": {"Read": {"xp": 25, "streak": 3}},
        }
        migrated = normalize_state(old)
        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["habits"]["Read"]["best_streak"], 3)
        self.assertEqual(migrated["habits"]["Read"]["last_done"], None)
        self.assertEqual(migrated["stats"]["completions"], 0)
        # 250 XP carries over and rolls into levels.
        self.assertEqual(migrated["level"], 2)
        self.assertEqual(migrated["xp"], 150)

    def test_normalize_handles_garbage(self):
        migrated = normalize_state({"xp": "not-a-number", "habits": ["bad"]})
        self.assertEqual(migrated["level"], 1)
        self.assertEqual(migrated["xp"], 0)
        self.assertEqual(migrated["habits"], {})

    def test_dashboard_payload(self):
        self.add("Read", 25)
        self.add("Run", 30)
        self.complete("Read")
        dashboard = build_dashboard(self.state, today=self.today)

        self.assertEqual(dashboard["hero"]["level"], 1)
        self.assertEqual(dashboard["hero"]["rank"], "Novice")
        self.assertEqual(dashboard["hero"]["next_rank"]["level"], 5)
        self.assertEqual(
            dashboard["hero"]["next_rank"]["xp_needed"],
            (100 - 27) + 200 + 300 + 400,
        )
        self.assertEqual(dashboard["boss"]["max"], 2)
        self.assertEqual(dashboard["boss"]["hp"], 1)
        self.assertEqual(dashboard["boss"]["remaining"], ["Run"])
        self.assertFalse(dashboard["boss"]["defeated"])
        self.assertEqual(len(dashboard["heatmap"]), 84)
        self.assertIn(self.today.isoformat(), [day["date"] for day in dashboard["heatmap"]])
        self.assertEqual(dashboard["stats"]["completed_today"], 1)
        self.assertFalse(dashboard["habits"][0]["done_today"])

    def test_heatmap_is_monday_aligned(self):
        days = heatmap_days(self.state, today=self.today)
        self.assertEqual(len(days), 84)
        first = date.fromisoformat(days[0]["date"])
        self.assertEqual(first.weekday(), 0)

    def test_boss_defeated_state(self):
        self.add("Read")
        self.complete("Read")
        dashboard = build_dashboard(self.state, today=self.today)
        self.assertTrue(dashboard["boss"]["defeated"])
        self.assertEqual(dashboard["boss"]["hp"], 0)
        self.assertEqual(dashboard["boss"]["remaining"], [])

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "state.json"
            self.add()
            self.complete()
            save_state(self.state, path)
            loaded = load_state(path)
            self.assertEqual(loaded["xp"], self.state["xp"])
            self.assertEqual(loaded["habits"]["Exercise"]["completions"], 1)

    def test_load_returns_fresh_state_for_broken_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_state(path), new_state())

    def test_demo_seed(self):
        state = new_state()
        seed_demo(state, today=self.today)
        dashboard = build_dashboard(state, today=self.today)
        self.assertEqual(state["hero_name"], "Aria the Emberbound")
        self.assertEqual(state["level"], 9)
        self.assertEqual(state["xp"], 640)
        self.assertEqual(len(state["habits"]), 5)
        self.assertEqual(dashboard["stats"]["completed_today"], 3)
        self.assertEqual(dashboard["boss"]["hp"], 2)
        self.assertTrue(any(item["unlocked"] for item in dashboard["achievements"]))
        self.assertEqual(len(dashboard["heatmap"]), 84)

    def test_cli_status_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--state", str(state_path), "add", "Read"]), 0)
                self.assertEqual(main(["--state", str(state_path), "add", "Read"]), 1)
                self.assertEqual(main(["--state", str(state_path), "status"]), 0)
                self.assertEqual(main(["--state", str(state_path), "undo"]), 1)
                self.assertEqual(main(["--state", str(state_path), "reset"]), 1)
                self.assertEqual(main(["--state", str(state_path), "reset", "--yes"]), 0)
            self.assertEqual(load_state(state_path)["habits"], {})


class TestWebApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "state.json"
        state = new_state()
        add_habit(state, "Read", 25)
        add_habit(state, "Run", 30)
        save_state(state, self.state_path)
        self.server = quest_web.create_server(
            self.state_path, host="127.0.0.1", port=0
        )
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def request(self, method, path, payload=None):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
        self.connection.request(method, path, body=body, headers=headers)
        response = self.connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        parsed = json.loads(raw) if "application/json" in content_type else raw
        return response.status, parsed

    def test_state_and_health(self):
        status, payload = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        status, dashboard = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["hero"]["name"], "Wanderer")
        self.assertEqual(dashboard["stats"]["quests"], 2)
        self.assertEqual(dashboard["state_path"], str(self.state_path))

    def test_complete_adds_xp(self):
        status, payload = self.request("POST", "/api/complete", {"habit": "Read"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["xp_awarded"], 27)
        read = next(
            item for item in payload["result"]["dashboard"]["habits"] if item["name"] == "Read"
        )
        self.assertTrue(read["done_today"])

        status, payload = self.request("POST", "/api/complete", {"habit": "Read"})
        self.assertEqual(status, 409)
        self.assertFalse(payload["ok"])

        status, payload = self.request("POST", "/api/complete", {"habit": "Nope"})
        self.assertEqual(status, 404)

    def test_add_rename_remove_and_undo(self):
        status, payload = self.request(
            "POST", "/api/add", {"name": "Write", "xp": 40}
        )
        self.assertEqual(status, 200)
        names = [item["name"] for item in payload["dashboard"]["habits"]]
        self.assertIn("Write", names)

        status, payload = self.request("POST", "/api/complete", {"habit": "Write"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["xp_awarded"], 42)

        status, payload = self.request("POST", "/api/undo")
        self.assertEqual(status, 200)
        self.assertEqual(payload["undone"]["habit"], "Write")
        write = next(
            item for item in payload["dashboard"]["habits"] if item["name"] == "Write"
        )
        self.assertFalse(write["done_today"])

        status, payload = self.request("POST", "/api/rename", {"name": "Borin"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["dashboard"]["hero"]["name"], "Borin")

        status, payload = self.request("POST", "/api/remove", {"habit": "Write"})
        self.assertEqual(status, 200)
        self.assertNotIn("Write", [item["name"] for item in payload["dashboard"]["habits"]])

    def test_validation_errors(self):
        status, payload = self.request("POST", "/api/add", {"name": ""})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

        status, payload = self.request("POST", "/api/complete", {"habit": 42})
        self.assertEqual(status, 400)

        status, payload = self.request("POST", "/api/unknown", {})
        self.assertEqual(status, 404)

    def test_demo_only_on_empty_save(self):
        status, _ = self.request("POST", "/api/demo")
        self.assertEqual(status, 400)  # this save already has quests

        with tempfile.TemporaryDirectory() as tmp:
            empty_path = Path(tmp) / "empty.json"
            save_state(new_state(), empty_path)
            empty_server = quest_web.create_server(empty_path, port=0)
            port = empty_server.server_address[1]
            thread = threading.Thread(target=empty_server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request(
                    "POST",
                    "/api/demo",
                    body="{}",
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(len(payload["dashboard"]["habits"]), 5)
            finally:
                connection.close()
                empty_server.shutdown()
                empty_server.server_close()
                thread.join(timeout=5)

    def test_static_dashboard_is_served(self):
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Habit Quest", body)
        self.assertIn(b"app.js", body)

        status, payload = self.request("GET", "/../habit_quest.py")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
