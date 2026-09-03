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

        bad_trip_qty = copy.deepcopy(self.data)
        bad_trip_qty["trips"][0]["items"][0]["qty"] = 0
        cases.append(bad_trip_qty)

        bad_audit = copy.deepcopy(self.data)
        bad_audit["trips"][0]["audit"] = {"Water": "probably"}
        cases.append(bad_audit)

        for invalid_data in cases:
            with self.subTest(data=invalid_data), self.assertRaises(gc.DataValidationError):
                gc.validate_data(invalid_data)

    def test_legacy_trip_quantities_are_migrated_without_weight_changes(self):
        data = gc.example_data()
        gear = data["gear"][0]
        gear["qty"] = 3
        entry = data["trips"][0]["items"][0]
        entry.pop("qty")
        gc.validate_data(data)
        self.assertEqual(entry["qty"], 3)
        self.assertEqual(data["meta"]["version"], gc.DATA_VERSION)
        self.assertEqual(gc.compute_trip_summary(data, data["trips"][0])["rows"][0]["total_oz"], 90)

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
    def test_weight_formatter_converts_and_signs_all_units(self):
        self.assertEqual(gc.format_weight_oz(0), "0.0 oz · 0.00 lb · 0.0 g")
        self.assertEqual(gc.format_weight_oz(16), "16.0 oz · 1.00 lb · 453.6 g")
        self.assertEqual(gc.format_weight_oz(2.6), "2.6 oz · 0.16 lb · 73.7 g")
        self.assertEqual(gc.format_weight_oz(-1, signed=True), "-1.0 oz · -0.06 lb · -28.3 g")
        self.assertEqual(gc.format_weight_oz(1, signed=True), "+1.0 oz · +0.06 lb · +28.3 g")

    def test_missing_gear_is_reported_without_breaking_summary(self):
        data = gc.example_data()
        data["trips"][0]["items"].append({"gear_id": "G999", "note": "missing"})
        summary = gc.compute_trip_summary(data, data["trips"][0])
        self.assertEqual(summary["missing_gear_ids"], ["G999"])
        self.assertIn("no longer exists", gc.render_trip_markdown(data, data["trips"][0]))

    def test_trip_quantity_overrides_inventory_quantity(self):
        data = gc.example_data()
        gear = data["gear"][2]
        gear["qty"] = 8
        entry = data["trips"][0]["items"][2]
        entry["qty"] = 2
        summary = gc.compute_trip_summary(data, data["trips"][0])
        row = next(row for row in summary["rows"] if row["gear"]["id"] == gear["id"])
        self.assertEqual(row["trip_qty"], 2)
        self.assertEqual(row["total_oz"], 5.2)
        self.assertEqual(summary["total_cost"], 450 + 550 + (45 * 2) + 25 + 170)
        self.assertIn("×2", gc.render_trip_markdown(data, data["trips"][0]))

    def test_zero_target_is_distinct_from_no_target(self):
        data = gc.example_data()
        trip = data["trips"][0]
        trip["target_base_weight_lb"] = 0.0
        summary = gc.compute_trip_summary(data, trip)
        self.assertEqual(summary["delta_lb"], summary["base_lb"])
        export = gc.render_trip_markdown(data, trip)
        self.assertIn("0.0 oz · 0.00 lb · 0.0 g", export)
        self.assertIn("over", export.lower())

    def test_inventory_value_uses_inventory_quantity(self):
        data = gc.example_data()
        data["gear"][0]["qty"] = 2
        export = gc.render_inventory_markdown(data)
        expected = sum(item["cost"] * item["qty"] for item in data["gear"])
        self.assertIn(f"${expected:,.2f} total value", export)
        self.assertIn("Cost / unit", export)

    def test_review_candidates_remain_in_export_with_pack_audit(self):
        data = gc.example_data()
        candidate = data["gear"][5]
        candidate["weight_oz"] = 9
        data["trips"][0]["items"].append({"gear_id": candidate["id"], "qty": 1, "note": ""})
        export = gc.render_trip_markdown(data, data["trips"][0])
        self.assertIn("## ⚠️ Review Candidates", export)
        self.assertIn("Low usefulness rating and meaningful weight", export)
        self.assertLess(export.index("## ⚠️ Review Candidates"), export.index("## Pack Audit"))

    def test_markdown_exports_show_ounces_pounds_and_grams(self):
        data = gc.example_data()
        for export in (
            gc.render_trip_markdown(data, data["trips"][0]),
            gc.render_inventory_markdown(data),
        ):
            with self.subTest(export=export[:40]):
                self.assertIn(" oz · ", export)
                self.assertIn(" lb · ", export)
                self.assertIn(" g", export)


class PlanningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.data = gc.example_data()
        self.trip = self.data["trips"][0]

    def test_duplicate_trip_is_independent_and_gets_next_id(self):
        duplicate = gc.duplicate_trip(self.data, self.trip)
        self.assertEqual(duplicate["id"], "T002")
        self.assertEqual(duplicate["name"], f"{self.trip['name']} (Copy)")
        duplicate["items"][0]["qty"] = 9
        duplicate["audit"]["Water"] = "omitted"
        self.assertEqual(self.trip["items"][0]["qty"], 1)
        self.assertNotIn("Water", self.trip["audit"])

    def test_duplicate_gear_is_independent_and_gets_next_id(self):
        source = self.data["gear"][0]
        duplicate = gc.duplicate_gear(self.data, source)
        self.assertEqual(duplicate["id"], "G007")
        self.assertEqual(duplicate["name"], f"{source['name']} (Copy)")
        duplicate["notes"] = "changed"
        self.assertNotEqual(source["notes"], duplicate["notes"])

    def test_compare_trips_reports_membership_quantity_and_weight_deltas(self):
        duplicate = gc.duplicate_trip(self.data, self.trip, "Alternative")
        duplicate["items"] = duplicate["items"][1:]
        duplicate["items"][0]["qty"] = 2
        duplicate["items"].append({"gear_id": "G006", "qty": 1, "note": ""})
        comparison = gc.compare_trips(self.data, self.trip, duplicate)
        self.assertEqual([row["gear_id"] for row in comparison["removed"]], ["G001"])
        self.assertEqual([row["gear_id"] for row in comparison["added"]], ["G006"])
        self.assertEqual(comparison["changed"][0]["gear_id"], "G002")
        self.assertEqual(comparison["changed"][0]["delta_oz"], 29.0)
        self.assertNotEqual(comparison["base_delta_lb"], 0)

    def test_pack_audit_distinguishes_packed_resolved_and_unresolved(self):
        self.trip["audit"] = {"Hygiene": "covered", "Repair/Tools": "omitted"}
        audit = gc.compute_pack_audit(self.data, self.trip)
        statuses = {row["category"]: row["status"] for row in audit["rows"]}
        self.assertEqual(statuses["Shelter"], "packed")
        self.assertEqual(statuses["Hygiene"], "covered")
        self.assertEqual(statuses["Repair/Tools"], "omitted")
        self.assertEqual(statuses["Miscellaneous"], "unresolved")
        export = gc.render_trip_markdown(self.data, self.trip)
        self.assertIn("## Pack Audit", export)
        self.assertIn("intentionally omitted", export)


if __name__ == "__main__":
    unittest.main()
