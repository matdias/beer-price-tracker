import asyncio
import csv
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Set
import httpx
from playwright.async_api import async_playwright

from .config import BREWERIES, MIN_DROP_PERCENT
from .normalizer import (
    is_valid_beer,
    extract_volume_and_qty,
    calculate_price_per_liter,
    build_beer_group,
)
from .stores import get_all_scrapers
from .notifier import dispatch_alerts

TZ_BRT = timezone(timedelta(hours=-3))
DATA_DIR = os.path.join("docs", "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.csv")
LOGS_PATH = os.path.join(DATA_DIR, "logs.json")


def make_product_id(store: str, url: str) -> str:
    raw = f"{store.lower()}::{url.strip().lower()}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def load_previous_snapshot() -> Set[str]:
    """Retorna os group_ids que estavam disponíveis na rodada imediatamente anterior."""
    if not os.path.exists(LATEST_PATH):
        return set()
    try:
        with open(LATEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            item["group_id"]
            for item in data.get("items", [])
            if item.get("available") and item.get("group_id")
        }
    except Exception:
        return set()


def load_historical_stats() -> tuple[Dict[str, float], Dict[str, float], Set[str]]:
    """
    Lê history.csv e retorna:
    - item_min_prices: {product_id: menor preço unitário histórico}
    - group_min_ppl: {group_id: menor R$/L histórico em qualquer loja/pack}
    - ever_seen_groups: conjunto de group_ids que já estiveram disponíveis alguma vez
    """
    item_min_prices: Dict[str, float] = {}
    group_min_ppl: Dict[str, float] = {}
    ever_seen_groups: Set[str] = set()

    if not os.path.exists(HISTORY_PATH):
        return item_min_prices, group_min_ppl, ever_seen_groups

    with open(HISTORY_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("id")
            gid = row.get("group_id")
            avail = row.get("available") == "True"
            if not avail:
                continue

            if gid:
                ever_seen_groups.add(gid)

            try:
                price = float(row.get("price", 0))
                if pid and price > 0:
                    if pid not in item_min_prices or price < item_min_prices[pid]:
                        item_min_prices[pid] = price
            except ValueError:
                pass

            try:
                ppl_raw = row.get("price_per_liter", "")
                if gid and ppl_raw:
                    ppl = float(ppl_raw)
                    if ppl > 0:
                        if gid not in group_min_ppl or ppl < group_min_ppl[gid]:
                            group_min_ppl[gid] = ppl
            except ValueError:
                pass

    return item_min_prices, group_min_ppl, ever_seen_groups


async def run():
    os.makedirs(DATA_DIR, exist_ok=True)
    now_brt = datetime.now(TZ_BRT)
    timestamp_iso = now_brt.isoformat(timespec="seconds")

    scrapers = get_all_scrapers()
    prev_available_groups = load_previous_snapshot()
    item_min_prices, group_min_ppl, ever_seen_groups = load_historical_stats()

    collected: Dict[str, Dict[str, Any]] = {}
    store_logs: List[Dict[str, Any]] = []

    async with async_playwright() as p, httpx.AsyncClient() as client:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
        )
        await context.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )

        try:
            for store in scrapers:
                store_count = 0
                errors = []

                for brewery, terms in BREWERIES.items():
                    for term in terms:
                        try:
                            raw_items = await store.search(client, term, context=context)
                            for item in raw_items:
                                title = item["title"]
                                if not is_valid_beer(title, brewery):
                                    continue

                                pid = make_product_id(store.name, item["url"])
                                if pid in collected:
                                    continue

                                vol_ml, qty = extract_volume_and_qty(title)
                                price_per_liter = calculate_price_per_liter(
                                    item["price"], vol_ml, qty
                                )
                                group_id, group_name = build_beer_group(title, brewery)

                                prev_item_min = item_min_prices.get(pid)
                                prev_grp_min_ppl = group_min_ppl.get(group_id)

                                drop_percent = 0.0
                                is_significant_drop = False
                                if (
                                    item["available"]
                                    and price_per_liter is not None
                                    and prev_grp_min_ppl is not None
                                    and prev_grp_min_ppl > 0
                                    and price_per_liter < prev_grp_min_ppl
                                ):
                                    drop_percent = round(
                                        ((prev_grp_min_ppl - price_per_liter) / prev_grp_min_ppl) * 100,
                                        1,
                                    )
                                    if drop_percent >= MIN_DROP_PERCENT:
                                        is_significant_drop = True

                                collected[pid] = {
                                    "id": pid,
                                    "group_id": group_id,
                                    "group_name": group_name,
                                    "brewery": brewery,
                                    "store": store.name,
                                    "title": title,
                                    "price": item["price"],
                                    "volume_ml": vol_ml,
                                    "quantity": qty,
                                    "price_per_liter": price_per_liter,
                                    "available": item["available"],
                                    "url": item["url"],
                                    "image": item["image"],
                                    "historical_min": min(prev_item_min, item["price"])
                                    if (prev_item_min and item["available"])
                                    else (item["price"] if item["available"] else prev_item_min),
                                    "group_min_ppl": min(prev_grp_min_ppl, price_per_liter)
                                    if (prev_grp_min_ppl and price_per_liter and item["available"])
                                    else (price_per_liter if item["available"] else prev_grp_min_ppl),
                                    "previous_group_min_ppl": prev_grp_min_ppl,
                                    "drop_percent": drop_percent,
                                    "is_price_drop": is_significant_drop,
                                    "updated_at": timestamp_iso,
                                }
                                store_count += 1

                            await asyncio.sleep(0.8)

                        except httpx.HTTPStatusError as exc:
                            errors.append(f"{term}: HTTP {exc.response.status_code}")
                        except Exception as exc:
                            if "WAF_IP_BLOCKED" in str(exc):
                                errors.append("WAF_IP_BLOCKED")
                                break
                            errors.append(f"{term}: {type(exc).__name__}")

                    if "WAF_IP_BLOCKED" in errors:
                        break

                status = "ok" if not errors else ("partial" if store_count > 0 else "error")
                store_logs.append({
                    "store": store.name,
                    "status": status,
                    "items_found": store_count,
                    "errors": errors[:5],
                    "checked_at": timestamp_iso,
                })
                print(f"[{store.name}] status={status} | itens={store_count} | erros={errors[:2]}")
        finally:
            await browser.close()

    items_list = sorted(
        collected.values(),
        key=lambda x: (
            not x["available"],
            x["price_per_liter"] if x["price_per_liter"] is not None else 999999,
            x["price"],
        ),
    )

    # Geração de alertas (1: Queda >= 10% no R$/L do grupo | 2: Retorno ao estoque do grupo)
    new_alerts: List[Dict[str, Any]] = []

    # Agrupa melhor oferta atual de cada group_id para evitar duplicar alertas na mesma rodada
    best_current_by_group: Dict[str, Dict[str, Any]] = {}
    for item in items_list:
        if not item["available"]:
            continue
        gid = item["group_id"]
        cur_best = best_current_by_group.get(gid)
        if cur_best is None:
            best_current_by_group[gid] = item
        else:
            p_new = item["price_per_liter"] if item["price_per_liter"] is not None else 9e9
            p_old = cur_best["price_per_liter"] if cur_best["price_per_liter"] is not None else 9e9
            if p_new < p_old:
                best_current_by_group[gid] = item

    for gid, best_item in best_current_by_group.items():
        if best_item["is_price_drop"]:
            new_alerts.append({
                "type": "price_drop",
                "timestamp": timestamp_iso,
                "group_id": gid,
                "group_name": best_item["group_name"],
                "brewery": best_item["brewery"],
                "store": best_item["store"],
                "title": best_item["title"],
                "url": best_item["url"],
                "current_price": best_item["price"],
                "current_ppl": best_item["price_per_liter"],
                "previous_min_ppl": best_item["previous_group_min_ppl"],
                "drop_percent": best_item["drop_percent"],
            })
        elif (
            prev_available_groups
            and gid in ever_seen_groups
            and gid not in prev_available_groups
        ):
            new_alerts.append({
                "type": "restock",
                "timestamp": timestamp_iso,
                "group_id": gid,
                "group_name": best_item["group_name"],
                "brewery": best_item["brewery"],
                "store": best_item["store"],
                "title": best_item["title"],
                "url": best_item["url"],
                "current_price": best_item["price"],
                "current_ppl": best_item["price_per_liter"],
                "previous_min_ppl": best_item["previous_group_min_ppl"],
                "drop_percent": 0.0,
            })

    await dispatch_alerts(new_alerts, timestamp_iso)

    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": timestamp_iso,
                "total_items": len(items_list),
                "items": items_list,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    with open(LOGS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": timestamp_iso, "stores": store_logs},
            f,
            ensure_ascii=False,
            indent=2,
        )

    file_exists = os.path.exists(HISTORY_PATH)
    with open(HISTORY_PATH, mode="a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "timestamp",
            "id",
            "group_id",
            "brewery",
            "store",
            "price",
            "price_per_liter",
            "available",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for item in items_list:
            writer.writerow({
                "timestamp": timestamp_iso,
                "id": item["id"],
                "group_id": item["group_id"],
                "brewery": item["brewery"],
                "store": item["store"],
                "price": item["price"],
                "price_per_liter": item["price_per_liter"] or "",
                "available": item["available"],
            })


if __name__ == "__main__":
    asyncio.run(run())
