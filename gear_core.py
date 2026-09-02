"""
gear_core.py — data model, persistence, and Markdown rendering for the
Backpacking Gear Tracker. Deliberately free of any UI code (no input(),
no print(), no Textual imports) so it can be driven by the TUI, a future
CLI, or a test script without dragging in a terminal.
"""

import copy
import json
import math
import os
import shutil
import tempfile
from datetime import date, datetime

CATEGORIES = [
    "Shelter", "Sleep System", "Pack", "Cook System", "Water",
    "Clothing - Worn", "Clothing - Carried", "Footwear", "Electronics",
    "Navigation & Safety", "First Aid", "Hygiene", "Repair/Tools",
    "Consumables/Food", "Miscellaneous",
]
WEIGHT_TYPES = ["Base Weight", "Worn Weight", "Consumable"]

CATEGORY_EMOJI = {
    "Shelter": "⛺", "Sleep System": "🛏️", "Pack": "🎒", "Cook System": "🍳",
    "Water": "💧", "Clothing - Worn": "👕", "Clothing - Carried": "🧥",
    "Footwear": "🥾", "Electronics": "🔋", "Navigation & Safety": "🧭",
    "First Aid": "⛑️", "Hygiene": "🧼", "Repair/Tools": "🔧",
    "Consumables/Food": "🍫", "Miscellaneous": "📦",
}
BIG_THREE = {"Shelter", "Sleep System", "Pack"}

REVIEW_WEIGHT_THRESHOLD_OZ = 8.0
REVIEW_USEFULNESS_THRESHOLD = 3
AUDIT_STATUSES = ("covered", "omitted", "unresolved")
DATA_VERSION = 2
GRAMS_PER_OUNCE = 28.349523125

class DataValidationError(ValueError):
    """Raised when a data file doesn't match Packrat's expected schema."""


class DataConflictError(OSError):
    """Raised rather than overwriting a data file changed by another process."""

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


def blank_data():
    return {
        "meta": {"created": date.today().isoformat(), "version": DATA_VERSION},
        "gear": [],
        "trips": [],
    }


def example_data():
    data = blank_data()
    data["gear"] = [
        {"id": "G001", "category": "Shelter", "name": "Solo Tent (EXAMPLE - delete me)",
         "brand": "Big Agnes Copper Spur HV1", "weight_oz": 30.0, "weight_type": "Base Weight",
         "qty": 1, "usefulness": 4, "cost": 450.0,
         "notes": "Includes stakes + guylines, no footprint", "added": date.today().isoformat()},
        {"id": "G002", "category": "Sleep System", "name": "Sleeping Bag (EXAMPLE - delete me)",
         "brand": "Western Mountaineering 20F", "weight_oz": 29.0, "weight_type": "Base Weight",
         "qty": 1, "usefulness": 5, "cost": 550.0,
         "notes": "Down, rated 20F - good for late Oct at elevation", "added": date.today().isoformat()},
        {"id": "G003", "category": "Cook System", "name": "Canister Stove (EXAMPLE - delete me)",
         "brand": "MSR PocketRocket 2", "weight_oz": 2.6, "weight_type": "Base Weight",
         "qty": 1, "usefulness": 4, "cost": 45.0,
         "notes": "Weighed without canister", "added": date.today().isoformat()},
        {"id": "G004", "category": "Water", "name": "Water Filter (EXAMPLE - delete me)",
         "brand": "Sawyer Squeeze", "weight_oz": 3.0, "weight_type": "Base Weight",
         "qty": 1, "usefulness": 5, "cost": 25.0,
         "notes": "", "added": date.today().isoformat()},
        {"id": "G005", "category": "Clothing - Worn", "name": "Rain Jacket (EXAMPLE - delete me)",
         "brand": "Outdoor Research Helium", "weight_oz": 6.4, "weight_type": "Worn Weight",
         "qty": 1, "usefulness": 4, "cost": 170.0,
         "notes": "Worn, not packed", "added": date.today().isoformat()},
        {"id": "G006", "category": "Electronics", "name": "Old Headlamp (EXAMPLE - delete me)",
         "brand": "Generic 3-LED", "weight_oz": 4.8, "weight_type": "Base Weight",
         "qty": 1, "usefulness": 2, "cost": 15.0,
         "notes": "Dim, unreliable switch - candidate to replace", "added": date.today().isoformat()},
    ]
    data["trips"] = [
        {"id": "T001", "name": "VA Triple Crown (EXAMPLE - delete me)", "dates": "Late October",
         "target_base_weight_lb": 15.0,
         "notes": "Mt. Rogers / Grayson Highlands / Wilburn Ridge loop, ~35 mi",
         "created": date.today().isoformat(),
         "audit": {},
         "items": [
             {"gear_id": "G001", "qty": 1, "note": ""},
             {"gear_id": "G002", "qty": 1, "note": ""},
             {"gear_id": "G003", "qty": 1, "note": ""},
             {"gear_id": "G004", "qty": 1, "note": ""},
             {"gear_id": "G005", "qty": 1, "note": "Worn, not packed"},
         ]},
    ]
    return data


def _number(value, field, *, minimum=0.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataValidationError(f"{field} must be a number")
    if not math.isfinite(value):
        raise DataValidationError(f"{field} must be finite")
    if value < minimum:
        raise DataValidationError(f"{field} must be at least {minimum:g}")
    return value


def validate_data(data):
    """Validate persisted data and add backward-compatible optional defaults.

    The function deliberately mutates ``data`` only to supply fields older files
    may not contain. Invalid or ambiguous values are rejected rather than being
    silently coerced and later producing incorrect pack weights.
    """
    if not isinstance(data, dict):
        raise DataValidationError("data file must contain a JSON object")
    if not isinstance(data.setdefault("meta", {}), dict):
        raise DataValidationError("meta must be an object")
    data["meta"].setdefault("created", date.today().isoformat())
    version = data["meta"].setdefault("version", DATA_VERSION)
    if not isinstance(data["meta"]["created"], str):
        raise DataValidationError("meta.created must be a string")
    if isinstance(version, bool) or not isinstance(version, int):
        raise DataValidationError("meta.version must be an integer")
    if version > DATA_VERSION:
        raise DataValidationError(
            f"data version {version} is newer than this Packrat supports ({DATA_VERSION})"
        )

    for collection in ("gear", "trips"):
        if not isinstance(data.setdefault(collection, []), list):
            raise DataValidationError(f"{collection} must be a list")

    gear_ids = set()
    for index, gear in enumerate(data["gear"]):
        label = f"gear[{index}]"
        if not isinstance(gear, dict):
            raise DataValidationError(f"{label} must be an object")
        gear_id = gear.get("id")
        if not isinstance(gear_id, str) or not gear_id.strip():
            raise DataValidationError(f"{label}.id must be a non-empty string")
        if gear_id in gear_ids:
            raise DataValidationError(f"duplicate gear id: {gear_id}")
        gear_ids.add(gear_id)
        for field in ("name", "category"):
            if not isinstance(gear.get(field), str) or not gear[field].strip():
                raise DataValidationError(f"{label}.{field} must be a non-empty string")
        if gear["category"] not in CATEGORIES:
            raise DataValidationError(
                f"{label}.category must be one of: {', '.join(CATEGORIES)}"
            )
        gear.setdefault("brand", "")
        gear.setdefault("notes", "")
        gear.setdefault("added", date.today().isoformat())
        if not all(isinstance(gear[field], str) for field in ("brand", "notes", "added")):
            raise DataValidationError(f"{label} text fields must be strings")
        _number(gear.get("weight_oz"), f"{label}.weight_oz")
        qty = _number(gear.get("qty"), f"{label}.qty", minimum=1)
        if not isinstance(qty, int):
            raise DataValidationError(f"{label}.qty must be an integer")
        usefulness = _number(gear.get("usefulness"), f"{label}.usefulness", minimum=1)
        if not isinstance(usefulness, int) or usefulness > 5:
            raise DataValidationError(f"{label}.usefulness must be an integer from 1 to 5")
        _number(gear.setdefault("cost", 0.0), f"{label}.cost")
        if gear.get("weight_type") not in WEIGHT_TYPES:
            raise DataValidationError(
                f"{label}.weight_type must be one of: {', '.join(WEIGHT_TYPES)}"
            )

    gear_by_id = {gear["id"]: gear for gear in data["gear"]}
    trip_ids = set()
    for index, trip in enumerate(data["trips"]):
        label = f"trips[{index}]"
        if not isinstance(trip, dict):
            raise DataValidationError(f"{label} must be an object")
        trip_id = trip.get("id")
        if not isinstance(trip_id, str) or not trip_id.strip():
            raise DataValidationError(f"{label}.id must be a non-empty string")
        if trip_id in trip_ids:
            raise DataValidationError(f"duplicate trip id: {trip_id}")
        trip_ids.add(trip_id)
        if not isinstance(trip.get("name"), str) or not trip["name"].strip():
            raise DataValidationError(f"{label}.name must be a non-empty string")
        trip.setdefault("dates", "")
        trip.setdefault("notes", "")
        trip.setdefault("created", date.today().isoformat())
        if not all(isinstance(trip[field], str) for field in ("dates", "notes", "created")):
            raise DataValidationError(f"{label} text fields must be strings")
        target = trip.setdefault("target_base_weight_lb", None)
        if target is not None:
            _number(target, f"{label}.target_base_weight_lb")
        audit = trip.setdefault("audit", {})
        if not isinstance(audit, dict):
            raise DataValidationError(f"{label}.audit must be an object")
        for category, status in audit.items():
            if category not in CATEGORIES:
                raise DataValidationError(f"{label}.audit contains unknown category: {category}")
            if status not in AUDIT_STATUSES:
                raise DataValidationError(
                    f"{label}.audit.{category} must be one of: {', '.join(AUDIT_STATUSES)}"
                )
        if not isinstance(trip.setdefault("items", []), list):
            raise DataValidationError(f"{label}.items must be a list")
        assigned = set()
        for item_index, entry in enumerate(trip["items"]):
            entry_label = f"{label}.items[{item_index}]"
            if not isinstance(entry, dict):
                raise DataValidationError(f"{entry_label} must be an object")
            gear_id = entry.get("gear_id")
            if not isinstance(gear_id, str) or not gear_id.strip():
                raise DataValidationError(f"{entry_label}.gear_id must be a non-empty string")
            if gear_id in assigned:
                raise DataValidationError(f"{label} assigns gear {gear_id} more than once")
            assigned.add(gear_id)
            default_qty = gear_by_id.get(gear_id, {}).get("qty", 1)
            qty = _number(entry.setdefault("qty", default_qty), f"{entry_label}.qty", minimum=1)
            if not isinstance(qty, int):
                raise DataValidationError(f"{entry_label}.qty must be an integer")
            entry.setdefault("note", "")
            if not isinstance(entry["note"], str):
                raise DataValidationError(f"{entry_label}.note must be a string")
    data["meta"]["version"] = DATA_VERSION
    return data


def load_data(path):
    path = os.fspath(path)
    if not os.path.exists(path):
        return example_data()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise DataValidationError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return validate_data(data)


def _atomic_write(path, content):
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def file_signature(path):
    path = os.fspath(path)
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


def save_data(path, data, expected_signature=None):
    path = os.fspath(path)
    validate_data(data)
    if expected_signature is not None and file_signature(path) != expected_signature:
        raise DataConflictError(
            "the data file changed on disk; restart Packrat to load the newer copy"
        )
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if os.path.exists(path):
        backup_data(path)
    _atomic_write(path, content)
    return file_signature(path)


def backup_data(path):
    """Create or replace a recoverable snapshot next to the data file."""
    path = os.fspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    backup_path = path + ".bak"
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".bak", dir=directory)
    os.close(fd)
    try:
        shutil.copy2(path, tmp_path)
        os.replace(tmp_path, backup_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
    return backup_path


def export_dir_for_data(data_path):
    """Keep exports with the selected portable data file."""
    return os.path.join(os.path.dirname(os.path.abspath(os.fspath(data_path))), "exports")


def write_export(path, content):
    path = os.fspath(path)
    _atomic_write(path, content)
    return path


def next_id(items, prefix):
    max_n = 0
    for it in items:
        iid = it.get("id", "")
        if iid.startswith(prefix):
            try:
                max_n = max(max_n, int(iid[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{max_n + 1:03d}"


def find_gear(data, gear_id):
    for g in data["gear"]:
        if g["id"] == gear_id:
            return g
    return None


def find_trip(data, trip_id):
    for t in data["trips"]:
        if t["id"] == trip_id:
            return t
    return None


def total_weight_oz(item):
    return round(item["weight_oz"] * item["qty"], 3)


def total_weight_lb(item):
    return round(total_weight_oz(item) / 16, 4)


def format_weight_oz(ounces, signed=False):
    """Format an ounce value in all display units without changing storage."""
    sign = "+" if signed else ""
    return (
        f"{format(ounces, sign + '.1f')} oz · "
        f"{format(ounces / 16, sign + '.2f')} lb · "
        f"{format(ounces * GRAMS_PER_OUNCE, sign + '.1f')} g"
    )


def trip_item_weight_oz(gear, entry):
    """Return the per-trip weight using the assignment quantity."""
    return round(gear["weight_oz"] * entry.get("qty", gear.get("qty", 1)), 3)


def is_review_flagged(item):
    return (item["usefulness"] < REVIEW_USEFULNESS_THRESHOLD
            and total_weight_oz(item) > REVIEW_WEIGHT_THRESHOLD_OZ)


def trips_referencing_gear(data, gear_id):
    return [t for t in data["trips"] if any(i["gear_id"] == gear_id for i in t["items"])]


def duplicate_trip(data, trip, name=None):
    """Return an independent copy of a trip with a fresh identity."""
    duplicate = copy.deepcopy(trip)
    duplicate["id"] = next_id(data["trips"], "T")
    duplicate["name"] = name or f"{trip['name']} (Copy)"
    duplicate["created"] = date.today().isoformat()
    return duplicate


def compute_pack_audit(data, trip):
    """Report category coverage without pretending every category is required."""
    packed_categories = {
        gear["category"]
        for entry in trip["items"]
        for gear in [find_gear(data, entry["gear_id"])]
        if gear is not None
    }
    saved = trip.get("audit", {})
    rows = []
    for category in CATEGORIES:
        status = "packed" if category in packed_categories else saved.get(category, "unresolved")
        rows.append({"category": category, "status": status})
    return {
        "rows": rows,
        "packed": sum(row["status"] == "packed" for row in rows),
        "covered": sum(row["status"] == "covered" for row in rows),
        "omitted": sum(row["status"] == "omitted" for row in rows),
        "unresolved": sum(row["status"] == "unresolved" for row in rows),
    }


def compare_trips(data, left, right):
    """Compare two loadouts by weight, category, membership, and quantity."""
    left_summary = compute_trip_summary(data, left)
    right_summary = compute_trip_summary(data, right)
    left_items = {entry["gear_id"]: entry for entry in left["items"]}
    right_items = {entry["gear_id"]: entry for entry in right["items"]}

    def item_row(gear_id, entry, side):
        gear = find_gear(data, gear_id)
        return {
            "gear_id": gear_id,
            "name": gear["name"] if gear else gear_id,
            "category": gear["category"] if gear else "Missing",
            "qty": entry.get("qty", gear.get("qty", 1) if gear else 1),
            "total_oz": trip_item_weight_oz(gear, entry) if gear else 0.0,
            "side": side,
        }

    added = [item_row(gid, right_items[gid], "right") for gid in right_items.keys() - left_items.keys()]
    removed = [item_row(gid, left_items[gid], "left") for gid in left_items.keys() - right_items.keys()]
    changed = []
    for gid in left_items.keys() & right_items.keys():
        gear = find_gear(data, gid)
        if gear is None:
            continue
        left_qty = left_items[gid].get("qty", gear.get("qty", 1))
        right_qty = right_items[gid].get("qty", gear.get("qty", 1))
        if left_qty != right_qty:
            changed.append({
                "gear_id": gid,
                "name": gear["name"],
                "category": gear["category"],
                "left_qty": left_qty,
                "right_qty": right_qty,
                "delta_oz": round((right_qty - left_qty) * gear["weight_oz"], 3),
            })

    category_deltas = {}
    for category in CATEGORIES:
        delta = right_summary["category_oz"].get(category, 0) - left_summary["category_oz"].get(category, 0)
        if delta:
            category_deltas[category] = round(delta, 2)

    return {
        "left": left_summary,
        "right": right_summary,
        "base_delta_lb": round(right_summary["base_lb"] - left_summary["base_lb"], 3),
        "total_delta_lb": round(right_summary["total_lb"] - left_summary["total_lb"], 3),
        "category_deltas": category_deltas,
        "added": sorted(added, key=lambda row: (-row["total_oz"], row["name"])),
        "removed": sorted(removed, key=lambda row: (-row["total_oz"], row["name"])),
        "changed": sorted(changed, key=lambda row: (-abs(row["delta_oz"]), row["name"])),
    }


def compute_trip_summary(data, trip):
    base_oz = worn_oz = consumable_oz = 0.0
    category_oz = {c: 0.0 for c in CATEGORIES}
    rows = []
    missing = []
    total_cost = 0.0

    for entry in trip["items"]:
        gear = find_gear(data, entry["gear_id"])
        if gear is None:
            missing.append(entry["gear_id"])
            continue
        oz = trip_item_weight_oz(gear, entry)
        if gear["weight_type"] == "Base Weight":
            base_oz += oz
        elif gear["weight_type"] == "Worn Weight":
            worn_oz += oz
        elif gear["weight_type"] == "Consumable":
            consumable_oz += oz
        if gear["category"] in category_oz:
            category_oz[gear["category"]] += oz
        total_cost += gear.get("cost", 0.0) or 0.0
        rows.append({
            "gear": gear,
            "trip_note": entry.get("note", ""),
            "trip_qty": entry.get("qty", gear.get("qty", 1)),
            "total_oz": oz,
            "review_flag": is_review_flagged(gear),
        })

    base_lb = base_oz / 16
    worn_lb = worn_oz / 16
    consumable_lb = consumable_oz / 16
    total_oz_all = base_oz + worn_oz + consumable_oz
    total_lb = total_oz_all / 16
    target_lb = trip.get("target_base_weight_lb")
    delta_lb = (base_lb - target_lb) if target_lb else None

    big_three_oz = sum(oz for cat, oz in category_oz.items() if cat in BIG_THREE)

    rows_sorted_by_weight = sorted(rows, key=lambda r: -r["total_oz"])

    return {
        "base_oz": round(base_oz, 2), "worn_oz": round(worn_oz, 2),
        "consumable_oz": round(consumable_oz, 2),
        "base_lb": round(base_lb, 3), "worn_lb": round(worn_lb, 3),
        "consumable_lb": round(consumable_lb, 3),
        "total_oz": round(total_oz_all, 2), "total_lb": round(total_lb, 3),
        "target_lb": target_lb,
        "delta_lb": round(delta_lb, 3) if delta_lb is not None else None,
        "category_oz": {k: round(v, 2) for k, v in category_oz.items() if v > 0},
        "big_three_oz": round(big_three_oz, 2),
        "big_three_lb": round(big_three_oz / 16, 3),
        "total_cost": round(total_cost, 2),
        "rows": rows,
        "rows_by_weight": rows_sorted_by_weight,
        "missing_gear_ids": missing,
        "item_count": len(rows),
        "unit_count": sum(row["trip_qty"] for row in rows),
        "audit": compute_pack_audit(data, trip),
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def bar(percent, width=22, filled_char="█", empty_char="░"):
    percent = max(0.0, min(100.0, percent))
    filled = round(percent / 100 * width)
    return filled_char * filled + empty_char * (width - filled)


def pct(part, whole):
    return (part / whole * 100) if whole else 0.0


def render_trip_markdown(data, trip):
    s = compute_trip_summary(data, trip)
    L = []
    add = L.append

    add(f"# 🏔️ {trip['name']}")
    add("")
    meta_bits = []
    if trip.get("dates"):
        meta_bits.append(f"**{trip['dates']}**")
    item_label = f"{s['item_count']} gear items"
    if s["unit_count"] != s["item_count"]:
        item_label += f" / {s['unit_count']} total units"
    meta_bits.append(item_label)
    if s["target_lb"]:
        meta_bits.append(f"target base **{format_weight_oz(s['target_lb'] * 16)}**")
    add(" · ".join(meta_bits))
    add("")
    if trip.get("notes"):
        add(f"> {trip['notes']}")
        add("")

    # --- Headline summary -------------------------------------------------
    add("## Summary")
    add("")
    status_line = ""
    if s["delta_lb"] is not None:
        if s["delta_lb"] <= 0:
            status_line = (
                f"✅ **{format_weight_oz(abs(s['delta_lb']) * 16)} under** your "
                f"{format_weight_oz(s['target_lb'] * 16)} base weight target"
            )
        else:
            status_line = (
                f"⚠️ **{format_weight_oz(s['delta_lb'] * 16)} over** your "
                f"{format_weight_oz(s['target_lb'] * 16)} base weight target"
            )
    add("| | Weight |")
    add("|---|---:|")
    add(f"| **Base weight** | **{format_weight_oz(s['base_oz'])}** |")
    add(f"| Worn weight | {format_weight_oz(s['worn_oz'])} |")
    add(f"| Consumable weight | {format_weight_oz(s['consumable_oz'])} |")
    add(f"| **Total pack weight** (skin-out) | **{format_weight_oz(s['total_oz'])}** |")
    if s["total_cost"]:
        add(f"| Total gear cost | ${s['total_cost']:,.2f} |")
    add("")
    if status_line:
        add(status_line)
        add("")

    if s["category_oz"] and s["base_oz"] + s["worn_oz"] + s["consumable_oz"] > 0:
        big3_pct = pct(s["big_three_oz"], s["total_oz"])
        add(f"**The Big Three** (shelter + sleep system + pack): "
            f"**{format_weight_oz(s['big_three_oz'])}** — {big3_pct:.0f}% of total pack weight")
        add("")

    # --- Weight distribution ------------------------------------------------
    if s["category_oz"]:
        add("## Weight Distribution")
        add("")
        add("| Category | Weight | % | |")
        add("|---|---:|---:|---|")
        max_oz = max(s["category_oz"].values())
        for cat, oz in sorted(s["category_oz"].items(), key=lambda kv: -kv[1]):
            pct_of_max = pct(oz, max_oz)
            emoji = CATEGORY_EMOJI.get(cat, "")
            add(f"| {emoji} {cat} | {format_weight_oz(oz)} | {pct(oz, s['total_oz']):.0f}% | `{bar(pct_of_max)}` |")
        add("")

    # --- Heaviest items -------------------------------------------------
    heaviest = [r for r in s["rows_by_weight"] if r["total_oz"] > 0][:5]
    if heaviest:
        add("## Heaviest Items")
        add("")
        for i, row in enumerate(heaviest, start=1):
            g = row["gear"]
            add(f"{i}. **{g['name']}** — {format_weight_oz(row['total_oz'])} ({g['category']})")
        add("")

    # --- Review candidates -------------------------------------------------
    review_rows = [r for r in s["rows"] if r["review_flag"]]
    if review_rows:
        add("## ⚠️ Review Candidates")
        add("")
        add("Low usefulness rating and meaningful weight — reconsider, replace, or cut:")
        add("")
        for row in sorted(review_rows, key=lambda r: -r["total_oz"]):
            g = row["gear"]
            add(f"- **{g['name']}** — {format_weight_oz(row['total_oz'])}, usefulness {g['usefulness']}/5")
        add("")

    # --- Pack audit ---------------------------------------------------------
    audit = s["audit"]
    add("## Pack Audit")
    add("")
    add(f"{audit['packed']} represented · {audit['covered']} covered elsewhere · "
        f"{audit['omitted']} intentionally omitted · {audit['unresolved']} unresolved")
    add("")
    unresolved = [row["category"] for row in audit["rows"] if row["status"] == "unresolved"]
    if unresolved:
        add("Unresolved categories: " + ", ".join(unresolved))
        add("")

    # --- Pack list ----------------------------------------------------------
    add("## Pack List")
    add("")
    by_cat = {}
    for row in s["rows"]:
        by_cat.setdefault(row["gear"]["category"], []).append(row)

    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        cat_oz = sum(r["total_oz"] for r in by_cat[cat])
        emoji = CATEGORY_EMOJI.get(cat, "")
        add(f"### {emoji} {cat} — {format_weight_oz(cat_oz)}")
        add("")
        for row in sorted(by_cat[cat], key=lambda r: -r["total_oz"]):
            g = row["gear"]
            brand = f" ({g['brand']})" if g.get("brand") else ""
            qty = f" ×{row['trip_qty']}" if row["trip_qty"] > 1 else ""
            flag = " ⚠️" if row["review_flag"] else ""
            note = f" — _{row['trip_note']}_" if row["trip_note"] else ""
            add(f"- [ ] {g['name']}{brand}{qty} — {format_weight_oz(row['total_oz'])}{note}{flag}")
        add("")

    if s["missing_gear_ids"]:
        add("## Warnings")
        add("")
        for gid in s["missing_gear_ids"]:
            add(f"- Item `{gid}` is on this trip but no longer exists in Gear Inventory.")
        add("")

    add("---")
    add(f"*Backpacking Gear Tracker · generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(L)


def render_inventory_markdown(data):
    L = []
    add = L.append
    gear = data["gear"]
    total_oz_all = sum(total_weight_oz(g) for g in gear)
    total_cost_all = sum(g.get("cost", 0.0) or 0.0 for g in gear)

    add("# 🎒 Gear Inventory")
    add("")
    add(f"{len(gear)} items · {format_weight_oz(total_oz_all)} total "
        f"· ${total_cost_all:,.2f} total value")
    add("")
    add(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    add("")

    by_cat = {}
    for g in gear:
        by_cat.setdefault(g["category"], []).append(g)

    if by_cat:
        add("## Weight by Category")
        add("")
        add("| Category | Weight | % | |")
        add("|---|---:|---:|---|")
        cat_totals = {c: sum(total_weight_oz(g) for g in items) for c, items in by_cat.items()}
        max_oz = max(cat_totals.values())
        for cat in CATEGORIES:
            if cat not in cat_totals:
                continue
            oz = cat_totals[cat]
            emoji = CATEGORY_EMOJI.get(cat, "")
            add(f"| {emoji} {cat} | {format_weight_oz(oz)} | {pct(oz, total_oz_all):.0f}% | "
                f"`{bar(pct(oz, max_oz))}` |")
        add("")

    flagged = [g for g in gear if is_review_flagged(g)]
    if flagged:
        add("## ⚠️ Review Candidates")
        add("")
        for g in sorted(flagged, key=lambda x: -total_weight_oz(x)):
            add(f"- **{g['name']}** — {format_weight_oz(total_weight_oz(g))}, usefulness {g['usefulness']}/5")
        add("")

    add("## Full Inventory")
    add("")
    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        cat_oz = cat_totals[cat]
        emoji = CATEGORY_EMOJI.get(cat, "")
        add(f"### {emoji} {cat} — {format_weight_oz(cat_oz)}")
        add("")
        add("| Item | Brand | Weight | Type | Qty | Useful. | Cost | |")
        add("|---|---|---:|---|---:|---:|---:|---|")
        for g in sorted(by_cat[cat], key=lambda x: -total_weight_oz(x)):
            flag = "⚠️" if is_review_flagged(g) else ""
            cost = f"${g['cost']:,.2f}" if g.get("cost") else ""
            add(f"| {g['name']} | {g.get('brand','')} | {format_weight_oz(total_weight_oz(g))} | "
                f"{g['weight_type']} | {g['qty']} | {g['usefulness']}/5 | {cost} | {flag} |")
        add("")

    add("---")
    add("*Backpacking Gear Tracker*")
    return "\n".join(L)


def safe_filename(name):
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in name)
    return keep.strip().replace(" ", "_") or "export"
