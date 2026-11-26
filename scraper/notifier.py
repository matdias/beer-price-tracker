import html
import json
import os
from typing import Dict, List, Any
import httpx

ALERTS_PATH = os.path.join("docs", "data", "alerts.json")
MAX_STORED_ALERTS = 60


def load_existing_alerts() -> List[Dict[str, Any]]:
    if not os.path.exists(ALERTS_PATH):
        return []
    try:
        with open(ALERTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("alerts", [])
    except Exception:
        return []


def save_alerts(alerts: List[Dict[str, Any]], updated_at: str) -> None:
    os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
    with open(ALERTS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "updated_at": updated_at,
                "alerts": alerts[:MAX_STORED_ALERTS],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _format_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_telegram_message(alert: Dict[str, Any]) -> str:
    title = html.escape(alert["title"])
    store = html.escape(alert["store"])
    group_name = html.escape(alert["group_name"])
    url = html.escape(alert["url"])

    if alert["type"] == "price_drop":
        curr_ppl = _format_brl(alert["current_ppl"])
        prev_ppl = _format_brl(alert["previous_min_ppl"])
        curr_price = _format_brl(alert["current_price"])
        drop_pct = f"{alert['drop_percent']:.1f}".replace(".", ",")

        return (
            f"🍺 <b>QUEDA DE PREÇO (-{drop_pct}%)</b>\n"
            f"<b>{group_name}</b>\n\n"
            f"📦 {title}\n"
            f"🏪 Loja: <b>{store}</b>\n"
            f"💰 Preço: <b>{curr_price}</b> (<b>{curr_ppl}/L</b>)\n"
            f"📉 Mínima anterior do rótulo: {prev_ppl}/L\n\n"
            f"🔗 <a href=\"{url}\">Abrir oferta na loja</a>"
        )

    # Retorno ao estoque (discreto)
    curr_price = _format_brl(alert["current_price"])
    ppl_part = f" ({_format_brl(alert['current_ppl'])}/L)" if alert.get("current_ppl") else ""
    return (
        f"📦 <i>Retorno ao estoque</i> — <b>{group_name}</b>\n"
        f"{title} • <b>{store}</b>\n"
        f"Valor: {curr_price}{ppl_part} • <a href=\"{url}\">Ver</a>"
    )


async def dispatch_alerts(
    new_alerts: List[Dict[str, Any]], timestamp_iso: str
) -> List[Dict[str, Any]]:
    existing = load_existing_alerts()
    if not new_alerts:
        if not os.path.exists(ALERTS_PATH):
            save_alerts([], timestamp_iso)
        return existing

    # Deduplicação recente: evita repetir exatamente o mesmo alerta nas últimas 24 entradas
    recent_signatures = {
        f"{a.get('type')}::{a.get('group_id')}::{a.get('store')}::{a.get('current_ppl')}"
        for a in existing[:25]
    }

    filtered_new = []
    for alert in new_alerts:
        sig = f"{alert['type']}::{alert['group_id']}::{alert['store']}::{alert['current_ppl']}"
        if sig not in recent_signatures:
            filtered_new.append(alert)
            recent_signatures.add(sig)

    if not filtered_new:
        return existing

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if token and chat_id:
        api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=15.0) as client:
            for alert in filtered_new:
                payload = {
                    "chat_id": chat_id,
                    "text": build_telegram_message(alert),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                }
                try:
                    resp = await client.post(api_url, json=payload)
                    resp.raise_for_status()
                except Exception as exc:
                    print(f"[Telegram] Falha ao enviar alerta ({alert['group_name']}): {exc}")
    else:
        print("[Telegram] Secrets não configurados; salvando alertas apenas no painel web.")

    merged = filtered_new + existing
    save_alerts(merged, timestamp_iso)
    return merged
