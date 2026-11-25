import re
import urllib.parse
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext
from .config import HEADERS
from .normalizer import parse_price_brl


class BaseStoreScraper:
    name: str = ""
    base_url: str = ""

    async def search(
        self, client: httpx.AsyncClient, term: str, context: Optional[BrowserContext] = None
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError


def _first_match(element, selectors: List[str]):
    for sel in selectors:
        found = element.select_one(sel)
        if found:
            return found
    return None


def parse_html_cards(soup: BeautifulSoup, base_url: str, store_name: str) -> List[Dict[str, Any]]:
    card_selectors = [
        ".listagem-item",          # Loja Integrada (Família Scopel, Piquiri Brewshop)
        ".spot-content",           # Wake / FBits (Clube do Malte)
        "ul.list-product li.item", # Tray (Nono Bier)
        ".product-card",           # Bagy (Costi Bebidas)
        "[data-product-id]",
        ".product-item",
        ".item-product",
        ".js-item-product",
        "li.product",
        ".showcase-item",
        ".produto",
    ]
    cards = []
    for sel in card_selectors:
        found = soup.select(sel)
        if len(found) > 0:
            cards = found
            break

    results = []
    seen_urls = set()

    for card in cards:
        a_tag = _first_match(
            card,
            [
                "a.produto-sobrepor",
                "a.nome-produto",
                "a.product-info",
                "a[href*='/produto/']",
                ".spot-content-title a",
                "a[href]",
            ],
        )
        if not a_tag:
            continue

        href = a_tag.get("href", "").strip()
        if not href or href.startswith("#") or "javascript:" in href:
            continue
        if href.startswith("/"):
            href = f"{base_url}{href}"
        href = href.split("?")[0]
        if href in seen_urls:
            continue

        title_el = _first_match(
            card,
            [
                ".nome-produto",
                ".spot-content-title h3",
                ".product-name",
                ".product-title",
                ".item-name",
                ".js-item-name",
                ".spot-title",
                ".produto-nome",
                "h2",
                "h3",
            ],
        )
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title:
            title = a_tag.get("title") or a_tag.get_text(" ", strip=True)

        # Extração de preço em ordem de prioridade + regex limpa
        price_el = _first_match(
            card,
            [
                ".preco-promocional",
                ".preco-venda",
                ".current-price",
                ".spot-price-avista",
                ".spot-price",
                ".price-promotional",
                ".js-price-display",
                ".sales-price",
                ".preco-avista",
                ".price",
                ".preco",
                "[data-product-price]",
            ],
        )
        raw_price = None
        if price_el:
            attr_price = price_el.get("data-product-price") or price_el.get("data-sell-price")
            if attr_price:
                raw_price = attr_price
            else:
                compact_text = re.sub(r"\s+", "", price_el.get_text())
                m = re.search(r"R\$(\d{1,3}(?:\.\d{3})*,\d{2})", compact_text)
                raw_price = m.group(1) if m else price_el.get_text(" ", strip=True)
        else:
            compact_card = re.sub(r"\s+", "", card.get_text())
            m = re.search(r"R\$(\d{1,3}(?:\.\d{3})*,\d{2})", compact_card)
            if m:
                raw_price = m.group(1)

        price = parse_price_brl(raw_price)

        # Remove banners ocultos antes de verificar disponibilidade
        card_clone = BeautifulSoup(str(card), "lxml")
        for hidden in card_clone.select(".sold-out-banner"):
            style = (hidden.get("style") or "").replace(" ", "").lower()
            if "display:block" not in style:
                hidden.decompose()

        card_text = card_clone.get_text(" ", strip=True).lower()
        out_of_stock = (
            "indisponivel" in " ".join(card.get("class", []))
            or any(
                w in card_text
                for w in ["esgotado", "indisponível", "indisponivel", "avise-me", "produto indisponível"]
            )
        )

        if not title or not price:
            continue

        img_el = card.select_one("img")
        img_url = ""
        if img_el:
            img_url = img_el.get("data-src") or img_el.get("src") or ""
            if img_url.startswith("//"):
                img_url = f"https:{img_url}"

        seen_urls.add(href)
        results.append({
            "store": store_name,
            "title": title.strip(),
            "price": price,
            "available": not out_of_stock,
            "url": href,
            "image": img_url,
        })

    return results


class ShopifySuggestScraper(BaseStoreScraper):
    """Casa Flora (API nativa Shopify)."""

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")

    async def search(
        self, client: httpx.AsyncClient, term: str, context: Optional[BrowserContext] = None
    ) -> List[Dict[str, Any]]:
        q = urllib.parse.quote(term)
        url = (
            f"{self.base_url}/search/suggest.json"
            f"?q={q}&resources[type]=product&resources[limit]=20"
        )
        resp = await client.get(url, headers=HEADERS, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()

        products = data.get("resources", {}).get("results", {}).get("products", [])
        results = []
        for p in products:
            price = parse_price_brl(p.get("price"))
            if not price:
                continue
            item_url = p.get("url", "")
            if item_url.startswith("/"):
                item_url = f"{self.base_url}{item_url}"

            results.append({
                "store": self.name,
                "title": p.get("title", "").strip(),
                "price": price,
                "available": bool(p.get("available", True)),
                "url": item_url.split("?")[0],
                "image": p.get("image") or p.get("featured_image", {}).get("url", ""),
            })
        return results


class VtexApiScraper(BaseStoreScraper):
    """Casa Santa Luzia (VTEX Catalog API)."""

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")

    async def search(
        self, client: httpx.AsyncClient, term: str, context: Optional[BrowserContext] = None
    ) -> List[Dict[str, Any]]:
        q = urllib.parse.quote(term)
        url = f"{self.base_url}/api/catalog_system/pub/products/search/{q}?_from=0&_to=24"
        resp = await client.get(url, headers=HEADERS, timeout=25.0)
        if resp.status_code not in (200, 206):
            resp.raise_for_status()

        data = resp.json()
        results = []
        for p in data:
            title = p.get("productName", "").strip()
            link = p.get("link", "")
            items = p.get("items", [])
            if not items:
                continue

            sku = items[0]
            images = sku.get("images", [])
            img_url = images[0].get("imageUrl", "") if images else ""
            sellers = sku.get("sellers", [])
            if not sellers:
                continue

            offer = sellers[0].get("commertialOffer", {})
            price = parse_price_brl(offer.get("Price"))
            avail_qty = offer.get("AvailableQuantity", 0)
            if not price and avail_qty == 0:
                price = parse_price_brl(offer.get("ListPrice"))
            if not price:
                continue

            results.append({
                "store": self.name,
                "title": title,
                "price": price,
                "available": avail_qty > 0,
                "url": link,
                "image": img_url,
            })
        return results


class HttpHtmlScraper(BaseStoreScraper):
    """Usado por lojas Loja Integrada (Família Scopel, Piquiri Brewshop) via HTTP direto."""

    def __init__(self, name: str, base_url: str, search_url_template: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.search_url_template = search_url_template

    async def search(
        self, client: httpx.AsyncClient, term: str, context: Optional[BrowserContext] = None
    ) -> List[Dict[str, Any]]:
        q = urllib.parse.quote_plus(term)
        url = self.search_url_template.format(query=q)
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=20.0)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        return parse_html_cards(soup, self.base_url, self.name)


class BrowserHtmlScraper(BaseStoreScraper):
    """Usa o contexto compartilhado do Playwright (Clube do Malte, Costi Bebidas, Nono Bier)."""

    def __init__(self, name: str, base_url: str, search_url_template: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.search_url_template = search_url_template
        self._warmed_up = False

    async def search(
        self, client: httpx.AsyncClient, term: str, context: Optional[BrowserContext] = None
    ) -> List[Dict[str, Any]]:
        if context is None:
            return []

        page = await context.new_page()
        try:
            if not self._warmed_up:
                await page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(1200)
                self._warmed_up = True

            q = urllib.parse.quote_plus(term)
            url = self.search_url_template.format(query=q)
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2000)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            page_title = soup.title.get_text(strip=True).lower() if soup.title else ""
            if "acesso bloqueado" in page_title or "default error page" in page_title:
                raise RuntimeError("WAF_IP_BLOCKED")

            return parse_html_cards(soup, self.base_url, self.name)
        finally:
            await page.close()


def get_all_scrapers() -> List[BaseStoreScraper]:
    return [
        ShopifySuggestScraper("Casa Flora", "https://www.casaflora.com.br"),
        VtexApiScraper("Casa Santa Luzia", "https://www.santaluzia.com.br"),
        HttpHtmlScraper(
            name="Família Scopel",
            base_url="https://loja.familiascopel.com.br",
            search_url_template="https://loja.familiascopel.com.br/buscar?q={query}",
        ),
        HttpHtmlScraper(
            name="Piquiri Brewshop",
            base_url="https://www.piquiribrewshop.com.br",
            search_url_template="https://www.piquiribrewshop.com.br/buscar?q={query}",
        ),
        BrowserHtmlScraper(
            name="Clube do Malte",
            base_url="https://www.clubedomalte.com.br",
            search_url_template="https://www.clubedomalte.com.br/busca?q={query}",
        ),
        BrowserHtmlScraper(
            name="Costi Bebidas",
            base_url="https://www.costibebidas.com.br",
            search_url_template="https://www.costibebidas.com.br/produtos?q={query}",
        ),
        BrowserHtmlScraper(
            name="Nono Bier",
            base_url="https://www.nonobier.com.br",
            search_url_template="https://www.nonobier.com.br/loja/busca.php?palavra_busca={query}",
        ),
    ]
