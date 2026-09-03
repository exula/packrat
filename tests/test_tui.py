import copy
import os
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Button, Checkbox, Input, Label, Static, TabbedContent

from gear_tui import (
    ConfirmScreen,
    GearFormScreen,
    GearTrackerApp,
    PackAuditScreen,
    PreferencesScreen,
    ShortcutHelpScreen,
    SetupApp,
    TripComparisonScreen,
    TripDashboardScreen,
    TripFormScreen,
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

    async def test_reload_library_accepts_valid_external_changes_and_rejects_invalid_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gear.json"
            app = GearTrackerApp(str(path))
            async with app.run_test(size=(120, 40)) as pilot:
                external = copy.deepcopy(app.data)
                external["gear"][0]["name"] = "Updated by sync"
                gc.save_data(path, external)
                app.query_one("#gear-table").focus()
                await pilot.press("ctrl+l")
                self.assertEqual(app.data["gear"][0]["name"], "Updated by sync")
                self.assertEqual(app._data_signature, gc.file_signature(path))

                await pilot.press("2")
                await pilot.click("#trip-open")
                self.assertIsInstance(app.screen, TripDashboardScreen)
                dashboard_update = copy.deepcopy(app.data)
                dashboard_update["trips"][0]["name"] = "Synced trip name"
                gc.save_data(path, dashboard_update)
                await pilot.press("ctrl+l")
                self.assertIn(
                    "Synced trip name",
                    str(app.screen.query_one("#dash-title", Static).render()),
                )
                await pilot.press("escape")

                valid_data = copy.deepcopy(app.data)
                valid_signature = app._data_signature
                path.write_text("{not valid json", encoding="utf-8")
                await pilot.press("ctrl+l")
                self.assertEqual(app.data, valid_data)
                self.assertEqual(app._data_signature, valid_signature)

    async def test_restore_backup_confirms_and_preserves_current_library(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gear.json"
            app = GearTrackerApp(str(path))
            original_name = app.data["gear"][0]["name"]
            app.data["gear"][0]["name"] = "Current unsatisfactory edit"
            self.assertTrue(app.save())
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.press("ctrl+shift+b")
                self.assertIsInstance(app.screen, ConfirmScreen)
                await pilot.click("#c-confirm")
                await pilot.pause()
                self.assertEqual(app.data["gear"][0]["name"], original_name)
                recovery = Path(f"{path}.before-restore.bak")
                self.assertTrue(recovery.exists())
                self.assertEqual(
                    gc.load_data(recovery)["gear"][0]["name"],
                    "Current unsatisfactory edit",
                )

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

    async def test_gear_duplicate_hotkey_creates_an_independent_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            app = GearTrackerApp(str(Path(directory) / "gear.json"))
            starting_count = len(app.data["gear"])
            async with app.run_test(size=(120, 40)) as pilot:
                table = app.query_one("#gear-table")
                table.focus()
                source_id = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
                source = copy.deepcopy(gc.find_gear(app.data, source_id))
                await pilot.press("d")
                self.assertEqual(len(app.data["gear"]), starting_count + 1)
                duplicate = app.data["gear"][-1]
                self.assertEqual(duplicate["id"], "G007")
                self.assertEqual(duplicate["name"], f"{source['name']} (Copy)")
                duplicate["notes"] = "variant-only"
                self.assertEqual(gc.find_gear(app.data, source_id)["notes"], source["notes"])

    async def test_forms_reject_non_finite_numbers_before_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            app = GearTrackerApp(str(Path(directory) / "gear.json"))
            starting_gear = copy.deepcopy(app.data["gear"])
            async with app.run_test(size=(100, 32)) as pilot:
                app.push_screen(GearFormScreen(mode="add"))
                await pilot.pause()
                app.screen.query_one("#f-name", Input).value = "Impossible item"
                app.screen.query_one("#f-weight", Input).value = "1e309"
                await pilot.press("ctrl+s")
                self.assertIsInstance(app.screen, GearFormScreen)
                self.assertEqual(app.data["gear"], starting_gear)
                await pilot.press("escape")

                app.push_screen(TripFormScreen(mode="add"))
                await pilot.pause()
                app.screen.query_one("#t-name", Input).value = "Impossible trip"
                app.screen.query_one("#t-target", Input).value = "1e309"
                await pilot.press("ctrl+s")
                self.assertIsInstance(app.screen, TripFormScreen)
                self.assertEqual(len(app.data["trips"]), 1)

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

    async def test_context_actions_follow_visible_content(self):
        with tempfile.TemporaryDirectory() as directory:
            app = GearTrackerApp(str(Path(directory) / "gear.json"))
            async with app.run_test(size=(120, 40)) as pilot:
                gear_search = app.query_one("#gear-search", Input)
                gear_search.value = "nothing could match this"
                await pilot.pause()
                self.assertTrue(app.query_one("#gear-edit", Button).disabled)
                self.assertTrue(app.query_one("#gear-duplicate", Button).disabled)
                self.assertTrue(app.query_one("#gear-delete", Button).disabled)
                self.assertIn("No matching gear", str(app.query_one("#gear-status", Static).render()))

                gear_search.value = ""
                await pilot.press("2")
                self.assertTrue(app.query_one("#trip-compare", Button).disabled)
                app.query_one("#trip-search", Input).value = "nothing could match this"
                await pilot.pause()
                self.assertTrue(app.query_one("#trip-open", Button).disabled)
                self.assertTrue(app.query_one("#trip-duplicate", Button).disabled)
                self.assertTrue(app.query_one("#trip-delete", Button).disabled)

                app.data["trips"][0]["items"] = []
                app.push_screen(TripDashboardScreen("T001"))
                await pilot.pause()
                self.assertTrue(app.screen.query_one("#dash-edit-item", Button).disabled)
                self.assertTrue(app.screen.query_one("#dash-remove-item", Button).disabled)
                self.assertFalse(app.screen.query_one("#dash-add-item", Button).disabled)
                self.assertIn(
                    "No gear assigned yet",
                    str(app.screen.query_one("#dash-items-heading", Static).render()),
                )
                await pilot.press("escape")

                app.data["trips"].clear()
                await pilot.press("3")
                self.assertTrue(app.query_one("#report-export-trip", Button).disabled)
                self.assertIn(
                    "full inventory export is still available",
                    str(app.query_one("#report-status", Static).render()),
                )


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

    async def test_first_run_can_create_blank_library(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / "blank-library"
            preference_path = Path(directory) / "config" / "preferences.json"
            app = SetupApp(preferences_path=str(preference_path))
            async with app.run_test(size=(100, 30)) as pilot:
                app.query_one("#setup-folder", Input).value = str(storage)
                app.query_one("#setup-examples", Checkbox).value = False
                await pilot.press("enter")

            data = gc.load_data(storage / preferences.DATA_FILENAME)
            self.assertEqual(data["gear"], [])
            self.assertEqual(data["trips"], [])

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

    async def test_open_create_can_start_with_blank_library(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original" / "gear.json"
            preference_path = Path(directory) / "config" / "preferences.json"
            destination = Path(directory) / "blank-library"
            app = GearTrackerApp(str(original), preferences_path=str(preference_path))

            async with app.run_test(size=(120, 40)) as pilot:
                app._change_library(("open", str(destination), False))

                self.assertEqual(app.data["gear"], [])
                self.assertEqual(app.data["trips"], [])
                self.assertEqual(
                    gc.load_data(destination / preferences.DATA_FILENAME)["gear"],
                    [],
                )

                self.assertIn(
                    "No gear yet",
                    str(app.query_one("#gear-status", Static).render()),
                )
                await pilot.press("2")
                self.assertIn(
                    "No trips yet",
                    str(app.query_one("#trip-status", Static).render()),
                )
                await pilot.press("3")
                self.assertIn(
                    "full inventory export is still available",
                    str(app.query_one("#report-status", Static).render()),
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
