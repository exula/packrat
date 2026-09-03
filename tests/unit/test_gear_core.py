"""Unit tests for gear_core.py"""

import json
import os
import tempfile
from datetime import date

import pytest

import gear_core as gc


def valid_gear(**overrides):
    gear = {
        "id": "G001",
        "category": "Shelter",
        "name": "Test",
        "brand": "",
        "weight_oz": 1.0,
        "weight_type": "Base Weight",
        "qty": 1,
        "usefulness": 3,
        "cost": 0.0,
        "notes": "",
        "added": date.today().isoformat(),
    }
    gear.update(overrides)
    return gear


class TestBlankData:
    """Test blank_data function."""

    def test_returns_empty_structure(self):
        data = gc.blank_data()
        assert data["meta"]["created"] == date.today().isoformat()
        assert data["meta"]["version"] == gc.DATA_VERSION
        assert data["gear"] == []
        assert data["trips"] == []


class TestExampleData:
    """Test example_data function."""

    def test_returns_populated_structure(self):
        data = gc.example_data()
        assert len(data["gear"]) == 6
        assert len(data["trips"]) == 1
        assert data["gear"][0]["id"] == "G001"
        assert data["gear"][0]["category"] == "Shelter"
        assert data["trips"][0]["id"] == "T001"
        assert data["trips"][0]["name"] == "VA Triple Crown (EXAMPLE - delete me)"


class TestLoadData:
    """Test load_data function."""

    def test_returns_example_data_for_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        data = gc.load_data(str(path))
        assert len(data["gear"]) == 6

    def test_rejects_empty_file(self, tmp_path):
        path = tmp_path / "empty.json"
        path.touch()
        with pytest.raises(gc.DataValidationError, match="invalid JSON"):
            gc.load_data(str(path))

    def test_loads_existing_file(self, tmp_path):
        path = tmp_path / "data.json"
        test_data = gc.blank_data()
        test_data["gear"] = [valid_gear()]
        with open(path, "w") as f:
            json.dump(test_data, f)
        data = gc.load_data(str(path))
        assert len(data["gear"]) == 1
        assert data["gear"][0]["id"] == "G001"

    def test_adds_defaults_to_missing_fields(self, tmp_path):
        path = tmp_path / "incomplete.json"
        test_data = {
            "meta": {"created": date.today().isoformat(), "version": 1},
            "gear": [{
                "id": "G001",
                "category": "Shelter",
                "name": "Test",
                "weight_oz": 1.0,
                "weight_type": "Base Weight",
                "qty": 1,
                "usefulness": 3,
            }],
        }
        with open(path, "w") as f:
            json.dump(test_data, f)
        data = gc.load_data(str(path))
        assert data["meta"]["created"] is not None
        assert data["meta"]["version"] == gc.DATA_VERSION
        assert data["gear"][0]["brand"] == ""
        assert data["gear"][0]["cost"] == 0.0
        assert data["gear"][0]["notes"] == ""
        assert data["trips"] == []


class TestSaveData:
    """Test save_data function."""

    def test_creates_parent_directory(self, tmp_path):
        path = tmp_path / "subdir" / "data.json"
        data = {"gear": []}
        gc.save_data(str(path), data)
        assert (tmp_path / "subdir" / "data.json").exists()

    def test_writes_valid_json(self, tmp_path):
        path = tmp_path / "data.json"
        data = gc.blank_data()
        data["gear"] = [valid_gear()]
        gc.save_data(str(path), data)
        with open(path) as f:
            saved = json.load(f)
        assert saved["gear"] == [valid_gear()]

    def test_atomic_write(self, tmp_path):
        path = tmp_path / "data.json"
        data = gc.blank_data()
        data["gear"] = [valid_gear()]
        gc.save_data(str(path), data)
        # Verify no .tmp file left behind
        assert not (tmp_path / "data.json.tmp").exists()


class TestNextId:
    """Test next_id function."""

    def test_generates_next_id_for_empty_list(self):
        assert gc.next_id([], "G") == "G001"

    def test_generates_next_id_for_existing_ids(self):
        items = [{"id": "G001"}, {"id": "G005"}, {"id": "G010"}]
        assert gc.next_id(items, "G") == "G011"

    def test_handles_invalid_ids(self):
        items = [{"id": "INVALID"}, {"id": "G001"}, {"id": "G002"}]
        assert gc.next_id(items, "G") == "G003"


class TestFindGear:
    """Test find_gear function."""

    def test_finds_existing_gear(self):
        data = {"gear": [{"id": "G001", "category": "Shelter"}]}
        result = gc.find_gear(data, "G001")
        assert result is not None
        assert result["id"] == "G001"

    def test_returns_none_for_missing_gear(self):
        data = {"gear": [{"id": "G001"}]}
        result = gc.find_gear(data, "G999")
        assert result is None


class TestFindTrip:
    """Test find_trip function."""

    def test_finds_existing_trip(self):
        data = {"trips": [{"id": "T001", "name": "Test Trip"}]}
        result = gc.find_trip(data, "T001")
        assert result is not None
        assert result["id"] == "T001"

    def test_returns_none_for_missing_trip(self):
        data = {"trips": [{"id": "T001"}]}
        result = gc.find_trip(data, "T999")
        assert result is None


class TestTotalWeight:
    """Test weight calculation functions."""

    def test_total_weight_oz(self):
        item = {"weight_oz": 10.0, "qty": 2}
        assert gc.total_weight_oz(item) == 20.0

    def test_total_weight_oz_rounding(self):
        item = {"weight_oz": 10.0, "qty": 3}
        result = gc.total_weight_oz(item)
        assert result == 30.0

    def test_total_weight_lb(self):
        item = {"weight_oz": 16.0, "qty": 1}
        assert gc.total_weight_lb(item) == 1.0

    def test_total_weight_lb_rounding(self):
        item = {"weight_oz": 17.0, "qty": 1}
        result = gc.total_weight_lb(item)
        assert result == 1.0625


class TestIsReviewFlagged:
    """Test is_review_flagged function."""

    def test_flagged_low_usefulness_high_weight(self):
        item = {"usefulness": 2, "weight_oz": 10.0, "qty": 1}
        assert gc.is_review_flagged(item) is True

    def test_not_flagged_high_usefulness(self):
        item = {"usefulness": 5, "weight_oz": 20.0, "qty": 1}
        assert gc.is_review_flagged(item) is False

    def test_not_flagged_low_weight(self):
        item = {"usefulness": 1, "weight_oz": 5.0, "qty": 1}
        assert gc.is_review_flagged(item) is False


class TestTripsReferencingGear:
    """Test trips_referencing_gear function."""

    def test_finds_all_refs(self):
        data = {
            "gear": [{"id": "G001"}],
            "trips": [
                {"id": "T001", "items": [{"gear_id": "G001"}]},
                {"id": "T002", "items": [{"gear_id": "G001"}]},
            ]
        }
        refs = gc.trips_referencing_gear(data, "G001")
        assert len(refs) == 2
        assert refs[0]["id"] == "T001"
        assert refs[1]["id"] == "T002"

    def test_no_refs(self):
        data = {
            "gear": [{"id": "G001"}],
            "trips": [{"id": "T001", "items": [{"gear_id": "G999"}]}]
        }
        refs = gc.trips_referencing_gear(data, "G001")
        assert refs == []


class TestComputeTripSummary:
    """Test compute_trip_summary function."""

    def test_basic_calculation(self):
        data = {
            "gear": [
                {"id": "G001", "category": "Shelter", "weight_oz": 30.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4},
                {"id": "G002", "category": "Sleep System", "weight_oz": 29.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 5},
            ],
            "trips": [{"id": "T001", "items": [{"gear_id": "G001"}, {"gear_id": "G002"}]}]
        }
        trip = data["trips"][0]
        summary = gc.compute_trip_summary(data, trip)
        assert summary["base_oz"] == 59.0
        assert summary["base_lb"] == 3.688  # 59/16 = 3.6875, rounded to 3 decimal places
        assert summary["item_count"] == 2

    def test_missing_gear(self):
        data = {
            "gear": [{"id": "G001", "category": "Shelter", "weight_oz": 30.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4}],
            "trips": [{"id": "T001", "items": [{"gear_id": "G001"}, {"gear_id": "G999"}]}]
        }
        summary = gc.compute_trip_summary(data, data["trips"][0])
        assert "G999" in summary["missing_gear_ids"]

    def test_category_breakdown(self):
        data = {
            "gear": [
                {"id": "G001", "category": "Shelter", "weight_oz": 30.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4},
                {"id": "G002", "category": "Cook System", "weight_oz": 5.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4},
            ],
            "trips": [{"id": "T001", "items": [{"gear_id": "G001"}, {"gear_id": "G002"}]}]
        }
        summary = gc.compute_trip_summary(data, data["trips"][0])
        assert summary["category_oz"]["Shelter"] == 30.0
        assert summary["category_oz"]["Cook System"] == 5.0

    def test_big_three_calculation(self):
        data = {
            "gear": [
                {"id": "G001", "category": "Shelter", "weight_oz": 30.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4},
                {"id": "G002", "category": "Sleep System", "weight_oz": 29.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 5},
                {"id": "G003", "category": "Pack", "weight_oz": 50.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4},
            ],
            "trips": [{"id": "T001", "items": [{"gear_id": "G001"}, {"gear_id": "G002"}, {"gear_id": "G003"}]}]
        }
        summary = gc.compute_trip_summary(data, data["trips"][0])
        assert summary["big_three_oz"] == 109.0
        assert summary["big_three_lb"] == 6.812  # 109/16 = 6.8125, rounded to 3 decimal places

    def test_weight_type_breakdown(self):
        data = {
            "gear": [
                {"id": "G001", "category": "Shelter", "weight_oz": 30.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4},
                {"id": "G002", "category": "Clothing - Worn", "weight_oz": 10.0, "weight_type": "Worn Weight", "qty": 1, "usefulness": 4},
                {"id": "G003", "category": "Food", "weight_oz": 20.0, "weight_type": "Consumable", "qty": 1, "usefulness": 4},
            ],
            "trips": [{"id": "T001", "items": [{"gear_id": "G001"}, {"gear_id": "G002"}, {"gear_id": "G003"}]}]
        }
        summary = gc.compute_trip_summary(data, data["trips"][0])
        assert summary["base_oz"] == 30.0
        assert summary["worn_oz"] == 10.0
        assert summary["consumable_oz"] == 20.0


class TestBar:
    """Test bar function."""

    def test_bar_100_percent(self):
        result = gc.bar(100.0)
        assert "█" in result
        assert "░" not in result

    def test_bar_0_percent(self):
        result = gc.bar(0.0)
        assert "█" not in result
        assert "░" in result

    def test_bar_clamped(self):
        assert gc.bar(-10.0) == gc.bar(0.0)
        assert gc.bar(110.0) == gc.bar(100.0)


class TestPct:
    """Test pct function."""

    def test_pct_calculation(self):
        assert gc.pct(50.0, 100.0) == 50.0

    def test_pct_zero_whole(self):
        assert gc.pct(50.0, 0.0) == 0.0


class TestRenderInventoryMarkdown:
    """Test render_inventory_markdown function."""

    def test_basic_render(self):
        data = gc.example_data()
        md = gc.render_inventory_markdown(data)
        assert "# 🎒 Gear Inventory" in md
        assert "Solo Tent" in md
        assert "Sleeping Bag" in md

    def test_render_empty_inventory(self):
        data = gc.blank_data()
        md = gc.render_inventory_markdown(data)
        assert "# 🎒 Gear Inventory" in md
        assert "0 items" in md


class TestRenderTripMarkdown:
    """Test render_trip_markdown function."""

    def test_basic_render(self):
        data = gc.example_data()
        trip = data["trips"][0]
        md = gc.render_trip_markdown(data, trip)
        assert f"# 🏔️ {trip['name']}" in md
        assert "Summary" in md
        assert "Base weight" in md

    def test_render_with_missing_gear(self):
        data = {
            "gear": [{"id": "G001", "category": "Shelter", "weight_oz": 30.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4, "name": "Test Item"}],
            "trips": [{"id": "T001", "name": "Test Trip", "items": [{"gear_id": "G001"}, {"gear_id": "G999"}]}]
        }
        md = gc.render_trip_markdown(data, data["trips"][0])
        assert "Warnings" in md
        assert "G999" in md

    def test_render_with_review_candidates(self):
        data = {
            "gear": [
                {"id": "G001", "category": "Shelter", "weight_oz": 30.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 2, "name": "Test Item"},
            ],
            "trips": [{"id": "T001", "name": "Test Trip", "items": [{"gear_id": "G001"}]}]
        }
        md = gc.render_trip_markdown(data, data["trips"][0])
        assert "Review Candidates" in md
        assert "Low usefulness rating and meaningful weight" in md

    def test_render_with_target_weight(self):
        data = {
            "gear": [{"id": "G001", "category": "Shelter", "weight_oz": 10.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4, "name": "Test Item"}],
            "trips": [{"id": "T001", "name": "Test Trip", "target_base_weight_lb": 5.0, "items": [{"gear_id": "G001"}]}]
        }
        md = gc.render_trip_markdown(data, data["trips"][0])
        assert "under" in md.lower()

    def test_render_over_target(self):
        data = {
            "gear": [{"id": "G001", "category": "Shelter", "weight_oz": 100.0, "weight_type": "Base Weight", "qty": 1, "usefulness": 4, "name": "Test Item"}],
            "trips": [{"id": "T001", "name": "Test Trip", "target_base_weight_lb": 5.0, "items": [{"gear_id": "G001"}]}]
        }
        md = gc.render_trip_markdown(data, data["trips"][0])
        assert "over" in md.lower()


class TestSafeFilename:
    """Test safe_filename function."""

    def test_basic_filename(self):
        assert gc.safe_filename("Test Trip") == "Test_Trip"

    def test_filename_with_special_chars(self):
        assert gc.safe_filename("Trip's Notes!") == "Trips_Notes"

    def test_empty_filename(self):
        assert gc.safe_filename("") == "export"

    def test_filename_with_underscores(self):
        assert gc.safe_filename("My_Trip") == "My_Trip"


class TestValidationError:
    """Test DataValidationError exception."""

    def test_raises_exception(self):
        with pytest.raises(gc.DataValidationError):
            raise gc.DataValidationError("Test error")
