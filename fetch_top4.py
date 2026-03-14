#!/usr/bin/env python3

# Copyright 2026 Chen-Yuanmeng <https://github.com/Chen-Yuanmeng>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


API_URL = "https://dmfw.mca.gov.cn/9095/xzqh/getList"
REQUEST_INTERVAL_SEC = 1.0 / 3.0  # 限速 3 次/秒
TIMEOUT_SEC = 25
MAX_RETRIES = 3
ROOT_CODE = "0"


class Top4Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS provinces (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cities (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                provinceCode TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS areas (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cityCode TEXT NOT NULL,
                provinceCode TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS streets (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                areaCode TEXT NOT NULL,
                cityCode TEXT NOT NULL,
                provinceCode TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS done_nodes (
                level TEXT NOT NULL,
                code TEXT NOT NULL,
                PRIMARY KEY(level, code)
            );
            """
        )
        self.conn.commit()

    def clear_all(self) -> None:
        self.conn.executescript(
            """
            DELETE FROM done_nodes;
            DELETE FROM streets;
            DELETE FROM areas;
            DELETE FROM cities;
            DELETE FROM provinces;
            """
        )
        self.conn.commit()

    def is_done(self, level: str, code: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM done_nodes WHERE level = ? AND code = ? LIMIT 1",
            (level, code),
        ).fetchone()
        return row is not None

    def mark_done(self, level: str, code: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO done_nodes(level, code) VALUES(?, ?)",
            (level, code),
        )
        self.conn.commit()

    def upsert_province(self, row: Dict[str, str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO provinces(code, name) VALUES(?, ?)",
            (row["code"], row["name"]),
        )

    def upsert_city(self, row: Dict[str, str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cities(code, name, provinceCode) VALUES(?, ?, ?)",
            (row["code"], row["name"], row["provinceCode"]),
        )

    def upsert_area(self, row: Dict[str, str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO areas(code, name, cityCode, provinceCode) VALUES(?, ?, ?, ?)",
            (row["code"], row["name"], row["cityCode"], row["provinceCode"]),
        )

    def upsert_street(self, row: Dict[str, str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO streets(code, name, areaCode, cityCode, provinceCode) VALUES(?, ?, ?, ?, ?)",
            (row["code"], row["name"], row["areaCode"], row["cityCode"], row["provinceCode"]),
        )

    def commit(self) -> None:
        self.conn.commit()

    def fetch_all(self, table_name: str, order_by: str = "code") -> List[Dict[str, str]]:
        cursor = self.conn.execute(f"SELECT * FROM {table_name} ORDER BY {order_by}")
        cols = [d[0] for d in cursor.description]
        rows: List[Dict[str, str]] = []
        for item in cursor.fetchall():
            rows.append({cols[i]: str(item[i]) for i in range(len(cols))})
        return rows

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


@dataclass
class ApiNode:
    code12: str
    name: str
    children: List["ApiNode"]

    @property
    def code2(self) -> str:
        return self.code12[:2]

    @property
    def code4(self) -> str:
        return self.code12[:4]

    @property
    def code6(self) -> str:
        return self.code12[:6]

    @property
    def code9(self) -> str:
        return self.code12[:9]


class McaClient:
    def __init__(self, interval_sec: float = REQUEST_INTERVAL_SEC, timeout_sec: int = TIMEOUT_SEC) -> None:
        self.interval_sec = interval_sec
        self.timeout_sec = timeout_sec
        self._last_call_at = 0.0
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://dmfw.mca.gov.cn/interface.html",
            }
        )

    def _wait_rate_limit(self) -> None:
        now = time.monotonic()
        delta = now - self._last_call_at
        if delta < self.interval_sec:
            time.sleep(self.interval_sec - delta)
        self._last_call_at = time.monotonic()

    def get_children(self, code: str, max_level: int = 1) -> List[ApiNode]:
        params = {"code": code, "maxLevel": max_level}  # 此处添加 year 参数可获取对应年份的历史数据，不加默认为最新数据
        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._wait_rate_limit()
                resp = self._session.get(API_URL, params=params, timeout=self.timeout_sec)
                resp.raise_for_status()
                payload = resp.json()
                status = payload.get("status")
                if status != 200:
                    raise RuntimeError(f"API status={status}, code={code}, maxLevel={max_level}, payload={payload}")
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise RuntimeError(f"invalid data type={type(data).__name__}, code={code}, maxLevel={max_level}")
                children = data.get("children") or []
                if not isinstance(children, list):
                    raise RuntimeError(f"invalid children type={type(children).__name__}, code={code}, maxLevel={max_level}")
                return [self._to_node(item) for item in children]
            except Exception as exc:  # pylint: disable=broad-except
                last_error = exc
                if attempt >= MAX_RETRIES:
                    break
                backoff = 2 ** (attempt - 1)
                print(
                    f"[warn] request failed for code={code}, maxLevel={max_level}, "
                    f"attempt={attempt}, backoff={backoff}s, err={exc}"
                )
                time.sleep(backoff)

            raise RuntimeError(f"request failed for code={code}, maxLevel={max_level}: {last_error}")

    def _to_node(self, item: Dict[str, Any]) -> ApiNode:
        code12 = str(item.get("code", ""))
        name = str(item.get("name", "")).strip()
        children_raw = item.get("children") or []
        children: List[ApiNode] = []
        if isinstance(children_raw, list):
            for child in children_raw:
                if isinstance(child, dict):
                    children.append(self._to_node(child))
        return ApiNode(code12=code12, name=name, children=children)


def is_city_level(code12: str) -> bool:
    return code12[4:] == "00000000" and code12[:4] != "0000"


def is_area_level(code12: str) -> bool:
    return code12[6:] == "000000" and code12[:6] != "000000" and not is_city_level(code12)


def is_street_level(code12: str) -> bool:
    return code12[9:] == "000" and code12[:9] != "000000000" and not is_area_level(code12)


def build_top4(
    client: McaClient,
    store: Top4Store,
    province_codes: Optional[List[str]] = None,
    max_provinces: Optional[int] = None,
    max_cities_per_province: Optional[int] = None,
    max_areas_per_city: Optional[int] = None,
) -> Dict[str, List[Dict[str, str]]]:
    province_nodes = client.get_children(ROOT_CODE)
    if province_codes:
        allowed = set(province_codes)
        province_nodes = [node for node in province_nodes if node.code2 in allowed]
    if max_provinces is not None:
        province_nodes = province_nodes[:max_provinces]

    municipality_codes = {"11", "12", "31", "50"}

    def upsert_direct_streets_for_city(city_node: ApiNode, city_code: str, city_name: str, province_code: str) -> int:
        direct_nodes = client.get_children(city_node.code12, max_level=2)
        direct_street_nodes = [node for node in direct_nodes if is_street_level(node.code12)]
        if not direct_street_nodes:
            return 0

        print(f"[info] fallback city={city_code} {city_name} use maxLevel=2 for direct streets")

        area_codes = sorted({node.code6 for node in direct_street_nodes})
        for area_code in area_codes:
            store.upsert_area(
                {
                    "code": area_code,
                    "name": city_name,
                    "cityCode": city_code,
                    "provinceCode": province_code,
                }
            )

        for node in direct_street_nodes:
            store.upsert_street(
                {
                    "code": node.code9,
                    "name": node.name,
                    "areaCode": node.code6,
                    "cityCode": city_code,
                    "provinceCode": province_code,
                }
            )

        store.commit()
        for area_code in area_codes:
            store.mark_done("area", area_code)

        return len(direct_street_nodes)

    for idx_p, province_node in enumerate(province_nodes, start=1):
        province_code = province_node.code2
        store.upsert_province({"code": province_code, "name": province_node.name})
        store.commit()
        print(f"[info] province {idx_p}/{len(province_nodes)} {province_code} {province_node.name}")

        if store.is_done("province", province_code):
            print(f"[resume] skip done province {province_code}")
            continue

        city_nodes = client.get_children(province_node.code12)

        # 直辖市无标准地级节点，补一条虚拟地级记录，保证四级结构完整。
        if province_code in municipality_codes:
            city_code = province_code + "01"
            city_name = "市辖区"
            print(
                f"[info] city {idx_p}/{len(province_nodes)} 1/1 "
                f"{city_code} {city_name} (province={province_code})"
            )
            store.upsert_city({"code": city_code, "name": city_name, "provinceCode": province_code})
            store.commit()

            if store.is_done("city", city_code):
                print(f"[resume] skip done city {city_code} {city_name}")
                store.mark_done("province", province_code)
                continue

            area_nodes = city_nodes
            if max_areas_per_city is not None:
                area_nodes = area_nodes[:max_areas_per_city]
            for area_node in area_nodes:
                area_code = area_node.code6
                store.upsert_area(
                    {
                        "code": area_code,
                        "name": area_node.name,
                        "cityCode": city_code,
                        "provinceCode": province_code,
                    }
                )
                store.commit()

                if store.is_done("area", area_code):
                    continue

                street_nodes = client.get_children(area_node.code12)
                for street_node in street_nodes:
                    if not is_street_level(street_node.code12):
                        continue
                    store.upsert_street(
                        {
                            "code": street_node.code9,
                            "name": street_node.name,
                            "areaCode": area_code,
                            "cityCode": city_code,
                            "provinceCode": province_code,
                        }
                    )
                store.commit()
                store.mark_done("area", area_code)

            store.mark_done("city", city_code)
            store.mark_done("province", province_code)
            continue

        if max_cities_per_province is not None:
            city_nodes = city_nodes[:max_cities_per_province]

        city_nodes = [city_node for city_node in city_nodes if is_city_level(city_node.code12)]

        total_cities = len(city_nodes)
        for idx_c, city_node in enumerate(city_nodes, start=1):
            city_code = city_node.code4
            print(
                f"[info] city {idx_p}/{len(province_nodes)} {idx_c}/{total_cities} "
                f"{city_code} {city_node.name} (province={province_code})"
            )
            store.upsert_city({"code": city_code, "name": city_node.name, "provinceCode": province_code})
            store.commit()

            if store.is_done("city", city_code):
                print(f"[resume] skip done city {city_code} {city_node.name}")
                continue

            area_nodes = client.get_children(city_node.code12)
            if max_areas_per_city is not None:
                area_nodes = area_nodes[:max_areas_per_city]

            area_nodes = [area_node for area_node in area_nodes if is_area_level(area_node.code12)]

            if not area_nodes:
                upsert_direct_streets_for_city(
                    city_node=city_node,
                    city_code=city_code,
                    city_name=city_node.name,
                    province_code=province_code,
                )
                store.mark_done("city", city_code)
                continue

            for area_node in area_nodes:
                area_code = area_node.code6
                store.upsert_area(
                    {
                        "code": area_code,
                        "name": area_node.name,
                        "cityCode": city_code,
                        "provinceCode": province_code,
                    }
                )
                store.commit()

                if store.is_done("area", area_code):
                    continue

                street_nodes = client.get_children(area_node.code12)
                for street_node in street_nodes:
                    if not is_street_level(street_node.code12):
                        continue
                    store.upsert_street(
                        {
                            "code": street_node.code9,
                            "name": street_node.name,
                            "areaCode": area_code,
                            "cityCode": city_code,
                            "provinceCode": province_code,
                        }
                    )
                store.commit()
                store.mark_done("area", area_code)

            store.mark_done("city", city_code)

        store.mark_done("province", province_code)

    return {
        "provinces": store.fetch_all("provinces"),
        "cities": store.fetch_all("cities"),
        "areas": store.fetch_all("areas"),
        "streets": store.fetch_all("streets"),
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)


def write_csv(path: Path, rows: Iterable[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_linkages(
    provinces: List[Dict[str, str]],
    cities: List[Dict[str, str]],
    areas: List[Dict[str, str]],
    streets: List[Dict[str, str]],
) -> Dict[str, Any]:
    cities_by_province: Dict[str, List[Dict[str, str]]] = {}
    for row in cities:
        cities_by_province.setdefault(row["provinceCode"], []).append(row)

    areas_by_city: Dict[str, List[Dict[str, str]]] = {}
    for row in areas:
        areas_by_city.setdefault(row["cityCode"], []).append(row)

    streets_by_area: Dict[str, List[Dict[str, str]]] = {}
    for row in streets:
        streets_by_area.setdefault(row["areaCode"], []).append(row)

    for values in cities_by_province.values():
        values.sort(key=lambda x: x["code"])
    for values in areas_by_city.values():
        values.sort(key=lambda x: x["code"])
    for values in streets_by_area.values():
        values.sort(key=lambda x: x["code"])

    pc: Dict[str, List[str]] = {}
    pca: Dict[str, Dict[str, List[str]]] = {}
    pcas: Dict[str, Dict[str, Dict[str, List[str]]]] = {}

    pc_code: List[Dict[str, Any]] = []
    pca_code: List[Dict[str, Any]] = []
    pcas_code: List[Dict[str, Any]] = []

    for province in provinces:
        p_code = province["code"]
        p_name = province["name"]
        city_list = cities_by_province.get(p_code, [])

        pc[p_name] = [c["name"] for c in city_list]

        province_code_node: Dict[str, Any] = {"code": p_code, "name": p_name, "children": []}
        province_code_node_pca: Dict[str, Any] = {"code": p_code, "name": p_name, "children": []}
        province_code_node_pcas: Dict[str, Any] = {"code": p_code, "name": p_name, "children": []}

        pca[p_name] = {}
        pcas[p_name] = {}

        for city in city_list:
            area_list = areas_by_city.get(city["code"], [])
            pca[p_name][city["name"]] = [a["name"] for a in area_list]

            city_node_for_pc = {"code": city["code"], "name": city["name"]}
            province_code_node["children"].append(city_node_for_pc)

            city_node_for_pca: Dict[str, Any] = {
                "code": city["code"],
                "name": city["name"],
                "children": [],
            }
            city_node_for_pcas: Dict[str, Any] = {
                "code": city["code"],
                "name": city["name"],
                "children": [],
            }

            pcas[p_name][city["name"]] = {}
            for area in area_list:
                street_list = streets_by_area.get(area["code"], [])
                pcas[p_name][city["name"]][area["name"]] = [s["name"] for s in street_list]

                city_node_for_pca["children"].append({"code": area["code"], "name": area["name"]})
                city_node_for_pcas["children"].append(
                    {
                        "code": area["code"],
                        "name": area["name"],
                        "children": [{"code": s["code"], "name": s["name"]} for s in street_list],
                    }
                )

            province_code_node_pca["children"].append(city_node_for_pca)
            province_code_node_pcas["children"].append(city_node_for_pcas)

        pc_code.append(province_code_node)
        pca_code.append(province_code_node_pca)
        pcas_code.append(province_code_node_pcas)

    return {
        "pc": pc,
        "pc-code": pc_code,
        "pca": pca,
        "pca-code": pca_code,
        "pcas": pcas,
        "pcas-code": pcas_code,
    }


def export_outputs(dist_dir: Path, dataset: Dict[str, List[Dict[str, str]]]) -> None:
    provinces = dataset["provinces"]
    cities = dataset["cities"]
    areas = dataset["areas"]
    streets = dataset["streets"]

    write_json(dist_dir / "provinces.json", provinces)
    write_json(dist_dir / "cities.json", cities)
    write_json(dist_dir / "areas.json", areas)
    write_json(dist_dir / "streets.json", streets)

    write_csv(dist_dir / "provinces.csv", provinces, ["code", "name"])
    write_csv(dist_dir / "cities.csv", cities, ["code", "name", "provinceCode"])
    write_csv(dist_dir / "areas.csv", areas, ["code", "name", "cityCode", "provinceCode"])
    write_csv(dist_dir / "streets.csv", streets, ["code", "name", "areaCode", "cityCode", "provinceCode"])

    linkage = build_linkages(provinces, cities, areas, streets)
    for name, payload in linkage.items():
        write_json(dist_dir / f"{name}.json", payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取中国四级行政区划（省/市/区县/乡镇）")
    parser.add_argument("--dist-dir", default="dist", help="输出目录，默认 dist")
    parser.add_argument("--db-path", default="checkpoints/top4.sqlite", help="SQLite 文件路径，默认 checkpoints/top4.sqlite")
    parser.add_argument("--reset-db", action="store_true", help="重置数据库后重新抓取")
    parser.add_argument(
        "--province-codes",
        default="",
        help="仅抓取指定省份代码，多个用逗号分隔，例如 46 或 44,46,62",
    )
    parser.add_argument("--max-provinces", type=int, default=None, help="仅抓取前 N 个省，便于快速测试")
    parser.add_argument("--max-cities-per-province", type=int, default=None, help="每省仅抓取前 N 个市")
    parser.add_argument("--max-areas-per-city", type=int, default=None, help="每市仅抓取前 N 个区县")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dist_dir = Path(os.path.abspath(args.dist_dir))
    db_path = Path(os.path.abspath(args.db_path))

    client = McaClient()
    store = Top4Store(db_path)
    province_codes = [item.strip() for item in args.province_codes.split(",") if item.strip()]
    try:
        if args.reset_db:
            print(f"[info] reset db: {db_path}")
            store.clear_all()

        dataset = build_top4(
            client=client,
            store=store,
            province_codes=province_codes or None,
            max_provinces=args.max_provinces,
            max_cities_per_province=args.max_cities_per_province,
            max_areas_per_city=args.max_areas_per_city,
        )
        export_outputs(dist_dir=dist_dir, dataset=dataset)
    finally:
        store.close()

    print("[done] export completed")
    print(
        json.dumps(
            {
                "provinces": len(dataset["provinces"]),
                "cities": len(dataset["cities"]),
                "areas": len(dataset["areas"]),
                "streets": len(dataset["streets"]),
                "dist": str(dist_dir),
                "db": str(db_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
