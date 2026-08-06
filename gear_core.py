"""
gear_core.py — data model, persistence, and Markdown rendering for the
Backpacking Gear Tracker. Deliberately free of any UI code (no input(),
no print(), no Textual imports) so it can be driven by the TUI, a future
CLI, or a test script without dragging in a terminal.
"""

import json
import os
from datetime import datetime, date

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(SCRIPT_DIR, "gear_data.json")
DEFAULT_EXPORT_DIR = os.path.join(SCRIPT_DIR, "exports")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


def blank_data():
    return {"meta": {"created": date.today().isoformat(), "version": 1}, "gear": [], "trips": []}


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
         "items": [
             {"gear_id": "G001", "note": ""},
             {"gear_id": "G002", "note": ""},
             {"gear_id": "G003", "note": ""},
             {"gear_id": "G004", "note": ""},
             {"gear_id": "G005", "note": "Worn, not packed"},
         ]},
    ]
    return data


def load_data(path):
    if not os.path.exists(path):
        return example_data()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("meta", {"created": date.today().isoformat(), "version": 1})
    data.setdefault("gear", [])
    data.setdefault("trips", [])
    return data


def save_data(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


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


def is_review_flagged(item):
    return (item["usefulness"] < REVIEW_USEFULNESS_THRESHOLD
            and total_weight_oz(item) > REVIEW_WEIGHT_THRESHOLD_OZ)


def trips_referencing_gear(data, gear_id):
    return [t for t in data["trips"] if any(i["gear_id"] == gear_id for i in t["items"])]


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
        oz = total_weight_oz(gear)
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
    meta_bits.append(f"{s['item_count']} items")
    if s["target_lb"]:
        meta_bits.append(f"target base **{s['target_lb']:.1f} lb**")
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
            status_line = f"✅ **{abs(s['delta_lb']):.2f} lb under** your {s['target_lb']:.1f} lb base weight target"
        else:
            status_line = f"⚠️ **{s['delta_lb']:.2f} lb over** your {s['target_lb']:.1f} lb base weight target"
    add("| | Weight |")
    add("|---|---:|")
    add(f"| **Base weight** | **{s['base_lb']:.2f} lb** ({s['base_oz']:.1f} oz) |")
    add(f"| Worn weight | {s['worn_lb']:.2f} lb ({s['worn_oz']:.1f} oz) |")
    add(f"| Consumable weight | {s['consumable_lb']:.2f} lb ({s['consumable_oz']:.1f} oz) |")
    add(f"| **Total pack weight** (skin-out) | **{s['total_lb']:.2f} lb** ({s['total_oz']:.1f} oz) |")
    if s["total_cost"]:
        add(f"| Total gear cost | ${s['total_cost']:,.2f} |")
    add("")
    if status_line:
        add(status_line)
        add("")

    if s["category_oz"] and s["base_oz"] + s["worn_oz"] + s["consumable_oz"] > 0:
        big3_pct = pct(s["big_three_oz"], s["total_oz"])
        add(f"**The Big Three** (shelter + sleep system + pack): "
            f"**{s['big_three_lb']:.2f} lb** — {big3_pct:.0f}% of total pack weight")
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
            add(f"| {emoji} {cat} | {oz:.1f} oz | {pct(oz, s['total_oz']):.0f}% | `{bar(pct_of_max)}` |")
        add("")

    # --- Heaviest items -------------------------------------------------
    heaviest = [r for r in s["rows_by_weight"] if r["total_oz"] > 0][:5]
    if heaviest:
        add("## Heaviest Items")
        add("")
        for i, row in enumerate(heaviest, start=1):
            g = row["gear"]
            add(f"{i}. **{g['name']}** — {row['total_oz']:.1f} oz ({g['category']})")
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
            add(f"- **{g['name']}** — {row['total_oz']:.1f} oz, usefulness {g['usefulness']}/5")
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
        add(f"### {emoji} {cat} — {cat_oz:.1f} oz ({cat_oz/16:.2f} lb)")
        add("")
        for row in sorted(by_cat[cat], key=lambda r: -r["total_oz"]):
            g = row["gear"]
            brand = f" ({g['brand']})" if g.get("brand") else ""
            qty = f" ×{g['qty']}" if g["qty"] > 1 else ""
            flag = " ⚠️" if row["review_flag"] else ""
            note = f" — _{row['trip_note']}_" if row["trip_note"] else ""
            add(f"- [ ] {g['name']}{brand}{qty} — {row['total_oz']:.1f} oz{note}{flag}")
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
    add(f"{len(gear)} items · {total_oz_all:.1f} oz total ({total_oz_all/16:.2f} lb) "
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
            add(f"| {emoji} {cat} | {oz:.1f} oz | {pct(oz, total_oz_all):.0f}% | "
                f"`{bar(pct(oz, max_oz))}` |")
        add("")

    flagged = [g for g in gear if is_review_flagged(g)]
    if flagged:
        add("## ⚠️ Review Candidates")
        add("")
        for g in sorted(flagged, key=lambda x: -total_weight_oz(x)):
            add(f"- **{g['name']}** — {total_weight_oz(g):.1f} oz, usefulness {g['usefulness']}/5")
        add("")

    add("## Full Inventory")
    add("")
    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        cat_oz = cat_totals[cat]
        emoji = CATEGORY_EMOJI.get(cat, "")
        add(f"### {emoji} {cat} — {cat_oz:.1f} oz ({cat_oz/16:.2f} lb)")
        add("")
        add("| Item | Brand | Wt (oz) | Type | Qty | Useful. | Cost | |")
        add("|---|---|---:|---|---:|---:|---:|---|")
        for g in sorted(by_cat[cat], key=lambda x: -total_weight_oz(x)):
            flag = "⚠️" if is_review_flagged(g) else ""
            cost = f"${g['cost']:,.2f}" if g.get("cost") else ""
            add(f"| {g['name']} | {g.get('brand','')} | {total_weight_oz(g):.1f} | "
                f"{g['weight_type']} | {g['qty']} | {g['usefulness']}/5 | {cost} | {flag} |")
        add("")

    add("---")
    add("*Backpacking Gear Tracker*")
    return "\n".join(L)


def safe_filename(name):
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in name)
    return keep.strip().replace(" ", "_") or "export"
