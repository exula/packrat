import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input, TabbedContent

from gear_tui import (
    GearFormScreen,
    GearTrackerApp,
    PackAuditScreen,
    ShortcutHelpScreen,
    TripComparisonScreen,
    TripDashboardScreen,
    TripItemFormScreen,
)


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

    async def test_duplicate_compare_quantity_and_audit_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            app = GearTrackerApp(str(Path(directory) / "gear.json"))
            async with app.run_test(size=(140, 48)) as pilot:
                await pilot.press("2")
                app.query_one("#trip-table").focus()
                await pilot.press("d")
                self.assertEqual(len(app.data["trips"]), 2)
                self.assertTrue(app.data["trips"][1]["name"].endswith("(Copy)"))

                await pilot.press("c")
                self.assertIsInstance(app.screen, TripComparisonScreen)
                await pilot.press("escape")

                await pilot.click("#trip-open")
                self.assertIsInstance(app.screen, TripDashboardScreen)
                app.screen.query_one("#dash-items-table").focus()
                await pilot.press("i")
                self.assertIsInstance(app.screen, TripItemFormScreen)
                app.screen.query_one("#ti-qty", Input).value = "3"
                await pilot.press("ctrl+s")
                self.assertEqual(app.data["trips"][1]["items"][0]["qty"], 3)

                await pilot.press("p")
                self.assertIsInstance(app.screen, PackAuditScreen)
                app.screen.query_one("#audit-table").focus()
                await pilot.press("down", "down", "space", "ctrl+s")
                self.assertTrue(app.data["trips"][1]["audit"])


if __name__ == "__main__":
    unittest.main()
