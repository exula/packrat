import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input, TabbedContent

from gear_tui import GearFormScreen, GearTrackerApp, ShortcutHelpScreen


class KeyboardWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_navigation_search_help_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gear.json"
            app = GearTrackerApp(str(path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.press("2")
                self.assertEqual(app.query_one(TabbedContent).active, "trips")
                await pilot.press("1", "/")
                self.assertEqual(app.query_one(TabbedContent).active, "gear")
                self.assertTrue(app.query_one("#gear-search", Input).has_focus)

                await pilot.press("a")
                self.assertEqual(app.query_one("#gear-search", Input).value, "a")
                self.assertNotIsInstance(app.screen, GearFormScreen)

                await pilot.press("escape", "?")
                self.assertIsInstance(app.screen, ShortcutHelpScreen)
                await pilot.press("escape", "ctrl+b")
                self.assertTrue(Path(f"{path}.bak").exists())

    async def test_gear_hotkey_and_ctrl_s_add_an_item(self):
        with tempfile.TemporaryDirectory() as directory:
            app = GearTrackerApp(str(Path(directory) / "gear.json"))
            starting_count = len(app.data["gear"])
            async with app.run_test(size=(120, 40)) as pilot:
                app.query_one("#gear-table").focus()
                await pilot.press("a")
                self.assertIsInstance(app.screen, GearFormScreen)
                await pilot.press("t", "e", "s", "t", "ctrl+s")
                self.assertEqual(len(app.data["gear"]), starting_count + 1)
                self.assertEqual(app.data["gear"][-1]["name"], "test")


if __name__ == "__main__":
    unittest.main()
