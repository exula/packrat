import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

import gear_core as gc


class DataValidationTests(unittest.TestCase):
    def setUp(self):
        self.data = gc.example_data()

    def test_example_data_is_valid(self):
        self.assertIs(gc.validate_data(self.data), self.data)

    def test_rejects_invalid_values(self):
        cases = []

        negative_weight = copy.deepcopy(self.data)
        negative_weight["gear"][0]["weight_oz"] = -1
        cases.append(negative_weight)

        bad_usefulness = copy.deepcopy(self.data)
        bad_usefulness["gear"][0]["usefulness"] = 6
        cases.append(bad_usefulness)

        duplicate_id = copy.deepcopy(self.data)
        duplicate_id["gear"][1]["id"] = duplicate_id["gear"][0]["id"]
        cases.append(duplicate_id)

        for invalid_data in cases:
            with self.subTest(data=invalid_data), self.assertRaises(gc.DataValidationError):
                gc.validate_data(invalid_data)

    def test_load_reports_json_location(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gear.json"
            path.write_text('{"gear": [}', encoding="utf-8")
            with self.assertRaisesRegex(gc.DataValidationError, r"line 1, column"):
                gc.load_data(path)


class PersistenceTests(unittest.TestCase):
    def test_save_is_atomic_keeps_backup_and_detects_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gear.json"
            original = gc.example_data()
            first_signature = gc.save_data(path, original)

            changed = copy.deepcopy(original)
            changed["gear"][0]["name"] = "Changed in Packrat"
            second_signature = gc.save_data(path, changed, expected_signature=first_signature)

            backup = Path(f"{path}.bak")
            self.assertTrue(backup.exists())
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), original)
            self.assertEqual(gc.load_data(path)["gear"][0]["name"], "Changed in Packrat")
            self.assertNotEqual(first_signature, second_signature)
            self.assertFalse(any(p.suffix == ".tmp" for p in Path(directory).iterdir()))

            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaises(gc.DataConflictError):
                gc.save_data(path, changed, expected_signature=second_signature)

    def test_exports_follow_custom_data_path(self):
        path = os.path.join("somewhere", "portable", "gear.json")
        self.assertEqual(
            gc.export_dir_for_data(path),
            os.path.abspath(os.path.join("somewhere", "portable", "exports")),
        )


class SummaryTests(unittest.TestCase):
    def test_missing_gear_is_reported_without_breaking_summary(self):
        data = gc.example_data()
        data["trips"][0]["items"].append({"gear_id": "G999", "note": "missing"})
        summary = gc.compute_trip_summary(data, data["trips"][0])
        self.assertEqual(summary["missing_gear_ids"], ["G999"])
        self.assertIn("no longer exists", gc.render_trip_markdown(data, data["trips"][0]))


if __name__ == "__main__":
    unittest.main()
