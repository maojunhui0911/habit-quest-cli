import unittest
from habit_quest import add_habit, complete_habit


class TestHabitQuest(unittest.TestCase):
    def test_add_and_complete_levels_up(self):
        state = {"xp": 0, "level": 1, "habits": {}}
        add_habit(state, "Exercise", xp=120)
        state, leveled_up = complete_habit(state, "Exercise")
        self.assertTrue(leveled_up)
        self.assertEqual(state["level"], 2)
        self.assertEqual(state["xp"], 20)
        self.assertEqual(state["habits"]["Exercise"]["streak"], 1)


if __name__ == "__main__":
    unittest.main()
