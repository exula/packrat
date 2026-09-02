import copy
import os
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Button, Input, Label, Static, TabbedContent

from gear_tui import (
    GearFormScreen,
    GearTrackerApp,
    PackAuditScreen,
    PreferencesScreen,
    ShortcutHelpScreen,
    SetupApp,
    TripComparisonScreen,
    TripDashboardScreen,
    TripItemFormScreen,
)
import gear_core as gc
import packrat_preferences as preferences


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

    async def test_compact_gear_form_keeps_actions_visible_and_previews_weight(self):
        with tempfile.TemporaryDirectory() as directory:
            app = GearTrackerApp(str(Path(directory) / "gear.json"))
            starting_count = len(app.data["gear"])
            async with app.run_test(size=(70, 20)) as pilot:
                app.query_one("#gear-table").focus()
                await pilot.press("a")
                form = app.screen
                form.query_one("#f-name", Input).value = "Compact test"
                form.query_one("#f-weight", Input).value = "16"
                await pilot.pause()

                preview = str(form.query_one("#f-weight-conversion", Label).render())
                self.assertIn("16.0 oz · 1.00 lb · 453.6 g", preview)
                save = form.query_one("#f-save", Button)
                form.query_one("#gear-form-fields").scroll_end(animate=False)
                await pilot.pause()
                self.assertTrue(save.is_on_screen)

                await pilot.click("#f-save")
                self.assertEqual(len(app.data["gear"]), starting_count + 1)
                self.assertEqual(app.data["gear"][-1]["weight_oz"], 16.0)

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


class PreferenceWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_run_creates_example_library_and_remembers_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / "library"
            preference_path = Path(directory) / "config" / "preferences.json"
            app = SetupApp(preferences_path=str(preference_path))
            async with app.run_test(size=(100, 30)) as pilot:
                folder = app.query_one("#setup-folder", Input)
                self.assertTrue(folder.has_focus)
                folder.value = str(storage)
                await pilot.press("enter")

            data_path = storage / preferences.DATA_FILENAME
            self.assertTrue(data_path.exists())
            self.assertTrue(gc.load_data(data_path)["gear"])
            self.assertEqual(
                preferences.load_preferences(preference_path),
                preferences.normalize_path(storage),
            )

    async def test_first_run_quit_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / "unused-library"
            preference_path = Path(directory) / "config" / "preferences.json"
            app = SetupApp(preferences_path=str(preference_path))
            async with app.run_test(size=(100, 30)) as pilot:
                app.query_one("#setup-folder", Input).value = str(storage)
                await pilot.click("#setup-quit")

            self.assertFalse(storage.exists())
            self.assertFalse(preference_path.exists())

    async def test_open_create_switches_library_and_updates_derived_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original" / "gear.json"
            preference_path = Path(directory) / "config" / "preferences.json"
            app = GearTrackerApp(str(original), preferences_path=str(preference_path))
            destination = Path(directory) / "other"

            async with app.run_test(size=(120, 40)):
                app._change_library(("open", str(destination)))

                expected = destination / preferences.DATA_FILENAME
                self.assertEqual(app.data_path, preferences.normalize_path(expected))
                self.assertEqual(
                    app.export_dir,
                    os.path.join(preferences.normalize_path(destination), "exports"),
                )
                self.assertEqual(
                    preferences.load_preferences(preference_path),
                    preferences.normalize_path(destination),
                )
                self.assertTrue(expected.exists())

    async def test_preferences_focuses_folder_and_enter_opens_library(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original" / "gear.json"
            preference_path = Path(directory) / "config" / "preferences.json"
            destination = Path(directory) / "keyboard-library"
            app = GearTrackerApp(str(original), preferences_path=str(preference_path))

            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.press("ctrl+p")
                self.assertIsInstance(app.screen, PreferencesScreen)
                folder = app.screen.query_one("#preferences-folder", Input)
                self.assertTrue(folder.has_focus)
                folder.value = str(destination)
                await pilot.press("enter")

                self.assertNotIsInstance(app.screen, PreferencesScreen)
                self.assertEqual(
                    app.data_path,
                    preferences.data_path_for_directory(destination),
                )

    async def test_copy_switch_preserves_source_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source" / "gear.json"
            preference_path = Path(directory) / "config" / "preferences.json"
            app = GearTrackerApp(str(source), preferences_path=str(preference_path))
            app.data["gear"][0]["name"] = "Current library marker"
            self.assertTrue(app.save())
            source_before = source.read_text(encoding="utf-8")
            destination = Path(directory) / "copy"

            async with app.run_test(size=(120, 40)):
                app._change_library(("copy", str(destination)))
                copied_path = destination / preferences.DATA_FILENAME
                self.assertEqual(gc.load_data(copied_path)["gear"][0]["name"], "Current library marker")
                self.assertEqual(source.read_text(encoding="utf-8"), source_before)

                first_destination_data = copy.deepcopy(app.data)
                second_destination = Path(directory) / "occupied"
                second_destination.mkdir()
                occupied_path = second_destination / preferences.DATA_FILENAME
                gc.save_data(occupied_path, gc.blank_data())
                current_path = app.data_path
                app._change_library(("copy", str(second_destination)))
                self.assertEqual(app.data_path, current_path)
                self.assertEqual(app.data, first_destination_data)
                self.assertEqual(gc.load_data(occupied_path)["gear"], [])

    async def test_invalid_library_rolls_back_path_data_and_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source" / "gear.json"
            preference_path = Path(directory) / "config" / "preferences.json"
            app = GearTrackerApp(str(source), preferences_path=str(preference_path))
            preferences.save_preferences(source.parent, preference_path)
            original_data = copy.deepcopy(app.data)
            invalid_directory = Path(directory) / "invalid"
            invalid_directory.mkdir()
            (invalid_directory / preferences.DATA_FILENAME).write_text("{bad json", encoding="utf-8")

            async with app.run_test(size=(120, 40)) as pilot:
                app._change_library(("open", str(invalid_directory)))
                await pilot.pause()
                self.assertEqual(app.data_path, preferences.normalize_path(source))
                self.assertEqual(app.data, original_data)
                self.assertEqual(
                    preferences.load_preferences(preference_path),
                    preferences.normalize_path(source.parent),
                )
                self.assertIsInstance(app.screen, PreferencesScreen)
                self.assertEqual(
                    app.screen.query_one("#preferences-folder", Input).value,
                    str(invalid_directory),
                )
                self.assertIn(
                    "Library switch failed",
                    str(app.screen.query_one("#preferences-error", Static).render()),
                )

    async def test_preference_write_failure_removes_new_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source" / "gear.json"
            blocking_file = Path(directory) / "not-a-config-directory"
            blocking_file.write_text("blocked", encoding="utf-8")
            preference_path = blocking_file / "preferences.json"
            app = GearTrackerApp(str(source), preferences_path=str(preference_path))
            destination = Path(directory) / "destination"
            original_path = app.data_path
            original_data = copy.deepcopy(app.data)

            async with app.run_test(size=(120, 40)):
                app._change_library(("copy", str(destination)))
                self.assertEqual(app.data_path, original_path)
                self.assertEqual(app.data, original_data)
                self.assertFalse((destination / preferences.DATA_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
