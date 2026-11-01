from typing import Optional, Tuple, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import engine
from app.models import WarehouseLocation, InventoryItem


def _norm_coord(val: Optional[str], prefixes: tuple) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip().upper()
    if s == "" or s == "NAN" or s == "NONE":
        return None
    if s.endswith(".0"):
        s = s[:-2].strip()
    for p in prefixes:
        if s.startswith(p):
            s = s[len(p):].strip()
    return s if s else None


def classify_brand_and_part(
    style: str,
    line: Optional[str] = None,
    row_pos: Optional[str] = None,
    section: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Determine (warehouse_part, brand, placement_type) from style code and location coordinates:
      - Part 1: Allbirds (14 Lines, 32-35 Sections, 4 Levels) -> styles starting with A, TB, TR, WR, TS, TA, Z1
      - Part 2: Von Dutch & Valentino (14 Rows, 36 Sections + FRONT/BACK/WALL, 4 Levels) -> VD*, VO*, V-*, EH*
    """
    st = (style or "").strip().upper()
    ln = (line or "").strip().upper()
    rw = (row_pos or "").strip().upper()
    sec = (section or "").strip().upper()

    # Determine brand from style prefix first
    if st.startswith("VD"):
        brand = "VON DUTCH"
    elif st.startswith("VO") or st.startswith("V-") or st.startswith("VAL"):
        brand = "VALENTINO"
    elif st.startswith("EH"):
        brand = "ED HARDY"
    elif st.startswith(("A1", "A2", "TB", "TR", "WR", "TS", "TA", "Z1", "WO", "WM")):
        brand = "ALLBIRDS"
    else:
        if rw and not ln:
            brand = "VON DUTCH"
        else:
            brand = "ALLBIRDS"

    # Determine Warehouse Part (PART_1 vs PART_2)
    if rw and not ln:
        warehouse_part = "PART_2"
    elif ln and not rw:
        warehouse_part = "PART_1"
    else:
        warehouse_part = "PART_2" if brand in ("VON DUTCH", "VALENTINO", "ED HARDY") else "PART_1"

    # Determine Placement Type (RACK vs GROUND_FRONT vs GROUND_BACK vs WALL)
    if rw == "WALL" or sec == "WALL" or ln == "WALL":
        placement_type = "WALL"
    elif sec == "FRONT":
        placement_type = "GROUND_FRONT"
    elif sec == "BACK":
        placement_type = "GROUND_BACK"
    else:
        placement_type = "RACK"

    return warehouse_part, brand, placement_type


def build_location_info(
    style: str,
    line: Optional[str] = None,
    section: Optional[str] = None,
    level: Optional[str] = None,
    row_pos: Optional[str] = None,
    box_num: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build standardized location strings, location_code, warehouse_part, brand, and placement_type.
    """
    ln = _norm_coord(line, ("LINE ", "LINE#", "LINE-", "LN ", "L-", "L"))
    sec = _norm_coord(section, ("SECTION ", "SECTION#", "SEC ", "SEC#", "SEC-", "S-"))
    lvl = _norm_coord(level, ("LEVEL ", "LEVEL#", "LVL ", "LVL#", "LVL-", "LV-", "LV"))
    rw = _norm_coord(row_pos, ("ROW ", "ROW#", "ROW-", "RW "))
    bx = _norm_coord(box_num, ("BOX #", "BOX#", "BOX ", "CARTONS ", "CARTON ", "CTN "))

    warehouse_part, brand, placement_type = classify_brand_and_part(style, ln, rw, sec)

    parts = []
    if warehouse_part == "PART_1":
        # Part 1: Allbirds (Line -> Section -> Level -> Box)
        if ln:
            parts.append(f"Line {ln}")
        if sec:
            parts.append(f"Sec {sec}")
        if lvl:
            parts.append(f"Lvl {lvl}")
        if bx:
            parts.append(f"Box {bx}")
        loc_code = f"P1-L{ln or '0'}-S{sec or '0'}-LV{lvl or '0'}"
    else:
        # Part 2: Von Dutch & Valentino (Row / Wall -> Section / Ground Front/Back -> Level -> Carton/Box)
        if rw == "WALL":
            parts.append("WALL")
        elif rw:
            parts.append(f"Row {rw}")
        elif ln:
            parts.append(f"Row {ln}")

        if sec == "FRONT":
            parts.append("Ground FRONT")
        elif sec == "BACK":
            parts.append("Ground BACK")
        elif sec == "WALL":
            parts.append("WALL")
        elif sec:
            parts.append(f"Sec {sec}")

        if lvl:
            parts.append(f"Lvl {lvl}")
        if bx:
            parts.append(f"Box {bx}")
        loc_code = f"P2-R{rw or ln or '0'}-S{sec or '0'}-LV{lvl or '0'}"

    display_str = " • ".join(parts) if parts else "Unassigned"
    return {
        "warehouse_part": warehouse_part,
        "brand": brand,
        "placement_type": placement_type,
        "location_code": loc_code,
        "location": display_str,
        "line": ln,
        "row_pos": rw,
        "section": sec,
        "level": lvl,
        "box_num": bx,
    }


def ensure_schema_and_locations_seeded(db: Session):
    """
    1. Safely add new columns (brand, warehouse_part, placement_type, location_code) to inventory_items if missing.
    2. Backfill any rows in inventory_items that haven't been classified yet.
    3. Seed the master warehouse_locations table for Part 1 (14 Lines x 35 Sections x 4 Levels)
       and Part 2 (14 Rows x 36 Sections + FRONT/BACK/WALL x 4 Levels) if empty.
    """
    for col_name, col_def in [
        ("brand", "VARCHAR(60) DEFAULT 'ALLBIRDS'"),
        ("warehouse_part", "VARCHAR(30) DEFAULT 'PART_1'"),
        ("placement_type", "VARCHAR(30) DEFAULT 'RACK'"),
        ("location_code", "VARCHAR(120)"),
    ]:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
        except Exception:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE inventory_items ADD COLUMN {col_name} {col_def}"))
            except Exception:
                pass

    needs_backfill = db.query(InventoryItem).filter(
        (InventoryItem.location_code.is_(None))
        | (InventoryItem.brand.is_(None))
        | (InventoryItem.location.like("%• Row %"))
    ).count()

    if needs_backfill > 0:
        print(f"[Warehouse Map] Backfilling 2-Zone location metadata on {needs_backfill:,} inventory rows...", flush=True)
        items = db.query(InventoryItem).all()
        for item in items:
            info = build_location_info(
                style=item.style,
                line=item.line,
                section=item.section,
                level=item.level,
                row_pos=item.row_pos,
                box_num=item.box_num,
            )
            item.warehouse_part = info["warehouse_part"]
            item.brand = info["brand"]
            item.placement_type = info["placement_type"]
            item.location_code = info["location_code"]
            item.location = info["location"]
        db.commit()
        print("[Warehouse Map] Backfill complete!", flush=True)

    loc_count = db.query(WarehouseLocation).count()
    if loc_count == 0:
        print("[Warehouse Map] Seeding 50,000 sq ft physical warehouse map (Part 1: 14 Lines, Part 2: 14 Rows + Front/Back/Wall)...", flush=True)
        master_locs = []
        seen_codes = set()

        # Part 1: Allbirds Zone -> 14 Lines x 35 Sections x 4 Levels
        for line_num in range(1, 15):
            for sec_num in range(1, 36):
                for lvl_num in range(1, 5):
                    code = f"P1-L{line_num}-S{sec_num}-LV{lvl_num}"
                    seen_codes.add(code)
                    master_locs.append({
                        "location_code": code,
                        "warehouse_part": "PART_1",
                        "zone_label": "Part 1: Allbirds (Lines 1-14)",
                        "aisle_type": "LINE",
                        "aisle_number": str(line_num),
                        "section": str(sec_num),
                        "level": str(lvl_num),
                        "placement_type": "RACK",
                        "display_location": f"Line {line_num} • Sec {sec_num} • Lvl {lvl_num}",
                    })

        # Part 2: Von Dutch & Valentino Zone -> 14 Rows x (FRONT, BACK, WALL, Sections 1..36) x 4 Levels
        for row_num in range(1, 15):
            for special_sec, p_type, label in [
                ("FRONT", "GROUND_FRONT", "Ground FRONT"),
                ("BACK", "GROUND_BACK", "Ground BACK"),
                ("WALL", "WALL", "WALL"),
            ]:
                for lvl_num in range(1, 5):
                    code = f"P2-R{row_num}-S{special_sec}-LV{lvl_num}"
                    seen_codes.add(code)
                    master_locs.append({
                        "location_code": code,
                        "warehouse_part": "PART_2",
                        "zone_label": "Part 2: Von Dutch & Valentino (Rows 1-14)",
                        "aisle_type": "ROW",
                        "aisle_number": str(row_num),
                        "section": special_sec,
                        "level": str(lvl_num),
                        "placement_type": p_type,
                        "display_location": f"Row {row_num} • {label} • Lvl {lvl_num}",
                    })
            for sec_num in range(1, 37):
                for lvl_num in range(1, 5):
                    code = f"P2-R{row_num}-S{sec_num}-LV{lvl_num}"
                    seen_codes.add(code)
                    master_locs.append({
                        "location_code": code,
                        "warehouse_part": "PART_2",
                        "zone_label": "Part 2: Von Dutch & Valentino (Rows 1-14)",
                        "aisle_type": "ROW",
                        "aisle_number": str(row_num),
                        "section": str(sec_num),
                        "level": str(lvl_num),
                        "placement_type": "RACK",
                        "display_location": f"Row {row_num} • Sec {sec_num} • Lvl {lvl_num}",
                    })

        # Dedicated Part 2 WALL aisle
        for special_sec in ("FRONT", "BACK", "WALL"):
            for lvl_num in range(1, 5):
                code = f"P2-RWALL-S{special_sec}-LV{lvl_num}"
                if code not in seen_codes:
                    seen_codes.add(code)
                    master_locs.append({
                        "location_code": code,
                        "warehouse_part": "PART_2",
                        "zone_label": "Part 2: Von Dutch & Valentino (Wall Zone)",
                        "aisle_type": "WALL",
                        "aisle_number": "WALL",
                        "section": special_sec,
                        "level": str(lvl_num),
                        "placement_type": "WALL",
                        "display_location": f"WALL • Sec {special_sec} • Lvl {lvl_num}",
                    })

        BATCH = 1000
        for i in range(0, len(master_locs), BATCH):
            db.bulk_insert_mappings(WarehouseLocation, master_locs[i:i + BATCH])
            db.commit()
        print(f"[Warehouse Map] Seeded {len(master_locs):,} physical warehouse locations!", flush=True)
