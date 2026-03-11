#!/usr/bin/env python3
"""
CSV → traveldestinations.json importer.

Usage:
    python3 import_destination_csv.py destinations.csv
    python3 import_destination_csv.py destinations.csv --dry-run   # preview only
    python3 import_destination_csv.py destinations.csv --replace   # overwrite existing city

CSV row types (first column determines the row type):
    Info    – destination header (one per city block)
    Hotel   – hotel entry
    Bar     – nightlife entry (Bar, Club, Sauna, Store)
    Tour    – tour entry
    Weather – general weather text + base fare range
    Month   – monthly weather (12 rows, 0-indexed in JSON)
    Event   – upcoming event
    Map     – add city to a mapping (region / country)
    Link    – add a gaycities / youtube link

Full column specs:
    Info,    <City Full Name>,  <IATA>,  <Flag Emoji>,  <LGBTQ Safety>,  <Safety Score>,  <Gay District>
    Hotel,   <Name>,            <Type: Luxury|Moderate|Boutique>,  <Tag1 | Tag2 | ...>
    Bar,     <Name>,            <Type: Bar|Club|Sauna|Store>,       <Tag1 | Tag2 | ...>
    Tour,    <Name>,            <Style>,                            <Price (optional)>
    Weather, <General Text>,    <Fare Min>,  <Fare Max>
    Month,   <0-11 index>,      <High temp>, <Low temp>,  <Summary>
    Event,   <Name>,            <Start YYYY-MM-DD>,  <End YYYY-MM-DD>
    Map,     <mapping key>,     <type: region|country|city>,        <city key to add>
    Link,    <city key>,        <type: gaycities|youtube>,          <url>
"""

import csv
import json
import sys
import argparse
from pathlib import Path
from copy import deepcopy

JSON_PATH = Path(__file__).parent / "traveldestinations.json"


def parse_tags(raw: str) -> list[str]:
    """Split 'Tag1 | Tag2 | Tag3' into ['Tag1', 'Tag2', 'Tag3']."""
    if not raw or not raw.strip():
        return []
    return [t.strip() for t in raw.split("|") if t.strip()]


def col(row: list[str], index: int, default: str = "") -> str:
    """Safe column access."""
    if index < len(row):
        return row[index].strip()
    return default


def load_json() -> dict:
    with open(JSON_PATH) as f:
        return json.load(f)


def save_json(data: dict) -> None:
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved → {JSON_PATH}")


def parse_csv(csv_path: str) -> list[dict]:
    """
    Read the CSV and group rows into destination blocks.
    Each block is a dict keyed by city_key containing parsed data.
    """
    blocks: list[dict] = []
    current: dict | None = None

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for raw_row in reader:
            # Strip all cells, skip blank rows and comment rows
            row = [c.strip() for c in raw_row]
            if not row or not row[0] or row[0].startswith("#"):
                continue

            row_type = row[0].strip().lower()

            # ── Info row starts a new destination block ──────────────────────
            if row_type == "info":
                if current:
                    blocks.append(current)
                full_name   = col(row, 1)
                iata        = col(row, 2).upper()
                image       = col(row, 3)        # flag emoji as text or HTML entity
                lgbtq_safety = col(row, 4)
                safety_score = col(row, 5)
                district     = col(row, 6)
                city_key     = full_name.split(",")[0].strip().lower()

                current = {
                    "_city_key":    city_key,
                    "name":         full_name,
                    "iata":         iata,
                    "image":        image,
                    "weather":      "",
                    "baseFare":     [0, 0],
                    "lgbtqSafety":  lgbtq_safety,
                    "safetyScore":  int(safety_score) if safety_score.isdigit() else 0,
                    "lgbtqDistrict": district,
                    "hotels":       [],
                    "nightlife":    [],
                    "tours":        [],
                    "events":       [],
                    "monthlyWeather": {},
                    "_maps":        [],   # Map rows buffered for mappings section
                    "_links":       [],   # Link rows buffered for destinationLinks
                }
                continue

            # All other row types require an active Info block
            if current is None:
                print(f"  WARNING: Row '{row}' appears before any Info row — skipped.")
                continue

            if row_type == "hotel":
                name  = col(row, 1)
                htype = col(row, 2, "Moderate")
                tags  = parse_tags(col(row, 3))
                current["hotels"].append({"name": name, "type": htype, "tags": tags})

            elif row_type == "bar":
                name   = col(row, 1)
                ntype  = col(row, 2, "Bar")
                tags   = parse_tags(col(row, 3))
                current["nightlife"].append({"name": name, "type": ntype, "tags": tags})

            elif row_type == "tour":
                name  = col(row, 1)
                style = col(row, 2, "Cultural")
                price = col(row, 3)
                entry: dict = {"name": name, "style": style}
                if price:
                    entry["price"] = price
                current["tours"].append(entry)

            elif row_type == "weather":
                current["weather"]  = col(row, 1)
                fare_min = col(row, 2)
                fare_max = col(row, 3)
                if fare_min and fare_max:
                    current["baseFare"] = [int(fare_min), int(fare_max)]

            elif row_type == "month":
                # Month index (0-11) or 3-letter abbreviation
                month_raw = col(row, 1)
                month_map = {
                    "jan": 0, "feb": 1, "mar": 2, "apr": 3,
                    "may": 4, "jun": 5, "jul": 6, "aug": 7,
                    "sep": 8, "oct": 9, "nov": 10, "dec": 11,
                }
                if month_raw.isdigit():
                    idx = int(month_raw)
                else:
                    idx = month_map.get(month_raw.lower()[:3], -1)

                if idx == -1:
                    print(f"  WARNING: Unknown month '{month_raw}' — skipped.")
                    continue

                high    = col(row, 2)
                low     = col(row, 3)
                summary = col(row, 4)
                current["monthlyWeather"][str(idx)] = {
                    "high":    high,
                    "low":     low,
                    "summary": summary,
                }

            elif row_type == "event":
                name  = col(row, 1)
                start = col(row, 2)
                end   = col(row, 3)
                current["events"].append({"name": name, "start": start, "end": end})

            elif row_type == "map":
                # Map, <mapping key>, <type: region|country|city>, <city key>
                mapping_key  = col(row, 1).lower()
                mapping_type = col(row, 2).lower()
                city_to_add  = col(row, 3).lower() or current["_city_key"]
                current["_maps"].append((mapping_type, mapping_key, city_to_add))

            elif row_type == "link":
                # Link, <city key (blank = current)>, <type>, <url>
                link_city = col(row, 1).lower() or current["_city_key"]
                link_type = col(row, 2).lower()
                link_url  = col(row, 3)
                current["_links"].append((link_city, link_type, link_url))

            else:
                print(f"  WARNING: Unknown row type '{row[0]}' — skipped.")

    if current:
        blocks.append(current)

    return blocks


def apply_blocks(data: dict, blocks: list[dict], replace: bool) -> dict:
    """Merge parsed CSV blocks into the loaded JSON data."""
    for block in blocks:
        city_key = block["_city_key"]

        if city_key in data and not replace:
            print(f"  SKIP '{city_key}' — already exists (use --replace to overwrite)")
            continue

        # Build the destination entry (strip internal helper keys)
        monthly = block.pop("monthlyWeather", {})
        maps    = block.pop("_maps", [])
        links   = block.pop("_links", [])
        city_key_internal = block.pop("_city_key")

        # Drop monthlyWeather if empty so we don't clobber existing data with {}
        if monthly:
            block["monthlyWeather"] = monthly

        # Drop events list if empty to stay consistent with existing cities
        if not block["events"]:
            block.pop("events", None)

        data[city_key_internal] = block
        print(f"  ADDED/UPDATED destination: '{city_key_internal}' ({block['name']})")

        # ── Mappings ─────────────────────────────────────────────────────────
        for (mtype, mkey, city) in maps:
            m = data.setdefault("mappings", {})
            section = m.setdefault(mtype + "s" if not mtype.endswith("s") else mtype, {})
            if mkey not in section:
                section[mkey] = []
            if city not in section[mkey]:
                section[mkey].append(city)
                print(f"    + mapping [{mtype}] '{mkey}' ← '{city}'")

        # Also add city aliases in mappings.cities
        iata_lc = block["iata"].lower()
        city_name_lc = city_key_internal
        cities_map = data.setdefault("mappings", {}).setdefault("cities", {})
        for alias in [city_name_lc, iata_lc]:
            if alias and alias not in cities_map:
                cities_map[alias] = [city_name_lc]
                print(f"    + city alias '{alias}' → '{city_name_lc}'")

        # ── destinationLinks ─────────────────────────────────────────────────
        for (link_city, link_type, link_url) in links:
            dl = data.setdefault("destinationLinks", {})
            if link_city not in dl:
                dl[link_city] = {}
            dl[link_city][link_type] = link_url
            print(f"    + link '{link_city}' [{link_type}] = {link_url}")

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Import a Pride Travel CSV into traveldestinations.json"
    )
    parser.add_argument("csv_file", help="Path to the CSV file to import")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and preview without writing to JSON"
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="Overwrite existing destinations instead of skipping them"
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    print(f"\nParsing CSV: {csv_path}")
    blocks = parse_csv(str(csv_path))
    print(f"  Found {len(blocks)} destination block(s)\n")

    if args.dry_run:
        print("── DRY RUN ─────────────────────────────────────────────────────────")
        for b in blocks:
            city_key = b["_city_key"]
            print(f"\n  [{city_key}] {b['name']} ({b['iata']})")
            print(f"    Hotels:    {len(b['hotels'])}")
            print(f"    Nightlife: {len(b['nightlife'])}")
            print(f"    Tours:     {len(b['tours'])}")
            print(f"    Events:    {len(b['events'])}")
            monthly = b.get("monthlyWeather", {})
            print(f"    Monthly weather rows: {len(monthly)}")
            print(f"    Maps:  {b['_maps']}")
            print(f"    Links: {b['_links']}")
        print("\nDry run complete. No files written.")
        return

    print(f"Loading JSON: {JSON_PATH}")
    data = load_json()

    print("Applying blocks…")
    data = apply_blocks(data, blocks, replace=args.replace)

    save_json(data)
    print("\nDone.")


if __name__ == "__main__":
    main()
