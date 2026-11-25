import asyncio
import csv
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
import httpx
from playwright.async_api import async_playwright

from .config import BREWERIES
from .normalizer import is_valid_beer, extract_volume_and_qty, calculate_price_per_liter
from .stores import get_all_scrapers

TZ_BRT = timezone(timedelta(hours=-3))
DATA_DIR = os.path.join("docs", "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.csv")
LOGS_PATH = os.path.join(DATA_DIR, "logs.json")


def make_product_id(store: str, url: str) -> str:
    raw = f"{store.lower()}::{url.strip().lower()}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def load_historical_min_prices() -> Dict[str, float]:
    min_prices: Dict[str, float] = {}
    if not os.path.exists(HISTORY_PATH):
        return min_prices

    with open(HISTORY_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("id")
            avail = row.get("available") == "True"
            try:
                price = float(row.get("price", 0))
            except ValueError:
                continue
            if pid and avail and price > 0:
                if pid not in min_prices or price < min_prices[pid]:
                    min_prices[pid] = price
    return min_prices


async def run():
    os.makedirs(DATA_DIR, exist_ok=True)
    now_brt = datetime.now(TZ_BRT)
    timestamp_iso = now_brt.isoformat(timespec="seconds")

    scrapers = get_all_scrapers()
    historical_mins = load_historical_min_prices()

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

                                prev_min = historical_mins.get(pid)
                                is_all_time_low = bool(
                                    item["available"]
                                    and prev_min is not None
                                    and item["price"] < prev_min
                                )

                                collected[pid] = {
                                    "id": pid,
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
                                    "historical_min": min(prev_min, item["price"])
                                    if (prev_min and item["available"])
                                    else (item["price"] if item["available"] else prev_min),
                                    "is_price_drop": is_all_time_low,
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
        fieldnames = ["timestamp", "id", "brewery", "store", "price", "price_per_liter", "available"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for item in items_list:
            writer.writerow({
                "timestamp": timestamp_iso,
                "id": item["id"],
                "brewery": item["brewery"],
                "store": item["store"],
                "price": item["price"],
                "price_per_liter": item["price_per_liter"] or "",
                "available": item["available"],
            })


if __name__ == "__main__":
    asyncio.run(run())
