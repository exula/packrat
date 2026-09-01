import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import packrat_preferences as preferences


class PreferencePersistenceTests(unittest.TestCase):
    def test_platform_paths_are_used(self):
        with patch("packrat_preferences.user_config_path") as config_path:
            config_path.return_value = Path("platform-config")
            self.assertEqual(
                preferences.preferences_file(),
                Path("platform-config") / "preferences.json",
            )
        with patch("packrat_preferences.user_data_path") as data_path:
            data_path.return_value = Path("platform-data")
            self.assertEqual(preferences.suggested_data_directory(), Path("platform-data"))

    def test_preferences_round_trip_normalizes_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            preference_path = Path(directory) / "config" / "preferences.json"
            relative_data_dir = Path(directory) / "data" / ".." / "gear"
            saved = preferences.save_preferences(relative_data_dir, preference_path)

            self.assertTrue(os.path.isabs(saved))
            self.assertEqual(preferences.load_preferences(preference_path), saved)
            payload = json.loads(preference_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], preferences.PREFERENCES_VERSION)
            self.assertEqual(payload["data_directory"], saved)
            self.assertFalse(any(path.suffix == ".tmp" for path in preference_path.parent.iterdir()))

    def test_missing_preferences_require_onboarding(self):
        with tempfile.TemporaryDirectory() as directory:
            preference_path = Path(directory) / "missing.json"
            self.assertIsNone(preferences.load_preferences(preference_path))
            self.assertIsNone(preferences.resolve_startup_data_path(None, preference_path))

    def test_malformed_preferences_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            preference_path = Path(directory) / "preferences.json"
            preference_path.write_text('{"version": 1,', encoding="utf-8")
            with self.assertRaisesRegex(preferences.PreferencesError, "line 1"):
                preferences.load_preferences(preference_path)

            preference_path.write_text(
                json.dumps({"version": 1, "data_directory": ""}), encoding="utf-8"
            )
            with self.assertRaisesRegex(preferences.PreferencesError, "non-empty"):
                preferences.load_preferences(preference_path)

    def test_cli_path_has_precedence_without_writing_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            preference_path = Path(directory) / "preferences.json"
            override = Path(directory) / "one-off.json"
            resolved = preferences.resolve_startup_data_path(override, preference_path)
            self.assertEqual(resolved, str(override.resolve()))
            self.assertFalse(preference_path.exists())

    def test_remembered_directory_resolves_fixed_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            preference_path = Path(directory) / "preferences.json"
            data_directory = Path(directory) / "library"
            preferences.save_preferences(data_directory, preference_path)
            self.assertEqual(
                preferences.resolve_startup_data_path(None, preference_path),
                str((data_directory / preferences.DATA_FILENAME).resolve()),
            )


if __name__ == "__main__":
    unittest.main()
