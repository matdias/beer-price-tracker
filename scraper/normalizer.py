import re
import unicodedata
from typing import Optional, Tuple
from .config import BREWERIES, NEGATIVE_KEYWORDS


def normalize_text(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def is_valid_beer(title: str, brewery: str) -> bool:
    norm_title = normalize_text(title)
    if not norm_title:
        return False

    for bad in NEGATIVE_KEYWORDS:
        if normalize_text(bad) in norm_title:
            return False

    terms = BREWERIES.get(brewery, [brewery.lower()])
    return any(normalize_text(t) in norm_title for t in terms)


def extract_volume_and_qty(title: str) -> Tuple[Optional[int], int]:
    norm = normalize_text(title)

    qty = 1
    qty_patterns = [
        r"(?:pack|kit|caixa|cx|fardo|c/|com)\s*(?:de\s*)?(\d{1,2})\b",
        r"\b(\d{1,2})\s*(?:un|unidades|garrafas|latas|long\s*neck)\b",
        r"\b(\d{1,2})\s*x\s*\d{2,4}\s*ml\b",
        r"\b\d{2,4}\s*ml\s*x\s*(\d{1,2})\b",
    ]
    for pat in qty_patterns:
        m = re.search(pat, norm)
        if m:
            val = int(m.group(1))
            if 1 < val <= 48:
                qty = val
                break

    vol_ml: Optional[int] = None

    m_ml = re.search(r"(\d{2,4})\s*ml\b", norm)
    if m_ml:
        vol_ml = int(m_ml.group(1))
    else:
        m_l = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:l|litros?)\b", norm)
        if m_l:
            liters = float(m_l.group(1).replace(",", "."))
            if 0.2 <= liters <= 10.0:
                vol_ml = int(round(liters * 1000))

    if vol_ml is None:
        if "long neck" in norm:
            vol_ml = 355
        elif "pint" in norm:
            vol_ml = 473

    return vol_ml, qty


def calculate_price_per_liter(
    price: float, volume_ml: Optional[int], quantity: int
) -> Optional[float]:
    if not price or not volume_ml or volume_ml <= 0:
        return None
    total_liters = (volume_ml * max(1, quantity)) / 1000.0
    return round(price / total_liters, 2)


def parse_price_brl(raw: str | float | int | None) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return round(val, 2) if val > 0 else None

    cleaned = re.sub(r"[^\d,.]", "", str(raw).strip())
    if not cleaned:
        return None

    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")

    try:
        val = float(cleaned)
        return round(val, 2) if val > 0 else None
    except ValueError:
        return None


def build_beer_group(title: str, brewery: str) -> Tuple[str, str]:
    """
    Normaliza títulos de diferentes lojas e embalagens (avulsa ou pack)
    para um mesmo identificador canônico (group_id, group_name).
    """
    norm = normalize_text(title)
    norm_brewery = normalize_text(brewery)

    # Remove termos de embalagem, quantidade, volume e palavras genéricas
    cleaned = norm
    noise_patterns = [
        r"\b(?:cerveja|importada|alema|alemã|belga|trapista|trappist|artesanal|premium)\b",
        r"\b(?:garrafa|lata|long\s*neck|pack|kit|caixa|cx|fardo|unidade|unidades|un)\b",
        r"\b(?:c/|com)\s*\d+\b",
        r"\b\d+\s*x\s*\d+\s*ml\b",
        r"\b\d+\s*ml\b",
        r"\b\d+(?:[.,]\d+)?\s*(?:l|litros?)\b",
        r"\b\d+\s*(?:un|garrafas|latas)\b",
    ]
    for pat in noise_patterns:
        cleaned = re.sub(pat, " ", cleaned)

    # Remove o nome da própria cervejaria para isolar o rótulo/estilo
    for term in BREWERIES.get(brewery, [brewery]):
        cleaned = re.sub(r"\b" + re.escape(normalize_text(term)) + r"\b", " ", cleaned)

    cleaned = re.sub(r"[^a-z0-9\s-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Normalização de aliases conhecidos por cervejaria
    alias_key = cleaned
    if norm_brewery == "schlenkerla":
        if "marzen" in cleaned:
            alias_key = "aecht rauchbier marzen"
        elif "weizen" in cleaned:
            alias_key = "aecht rauchbier weizen"
        elif "urbock" in cleaned:
            alias_key = "aecht rauchbier urbock"
        elif "fastenbier" in cleaned:
            alias_key = "aecht rauchbier fastenbier"
        elif "eiche" in cleaned:
            alias_key = "eiche doppelbock"
        elif "hansla" in cleaned:
            alias_key = "hansla"
        elif "helles" in cleaned or "lager" in cleaned:
            alias_key = "helles lagerbier"
    elif norm_brewery == "paulaner":
        if "weiss" in cleaned or "hefe" in cleaned:
            alias_key = "hefe-weissbier"
        elif "dunkel" in cleaned:
            alias_key = "weissbier dunkel"
        elif "munchner" in cleaned or "hell" in cleaned or "lager" in cleaned:
            alias_key = "munchner hell"
        elif "salvator" in cleaned:
            alias_key = "salvator doppelbock"
        elif "oktoberfest" in cleaned:
            alias_key = "oktoberfest bier"
    elif norm_brewery == "duvel":
        if "666" in cleaned:
            alias_key = "666"
        elif "tripel hop" in cleaned or "citra" in cleaned or "cashmere" in cleaned:
            alias_key = "tripel hop"
        else:
            alias_key = "belgian golden strong ale"
    elif norm_brewery == "de halve maan":
        if "quadrupel" in cleaned or "11" in cleaned:
            alias_key = "straffe hendrik quadrupel"
        elif "tripel" in cleaned or "9" in cleaned:
            alias_key = "straffe hendrik tripel"
        elif "blond" in cleaned or "blonde" in cleaned:
            alias_key = "brugse zot blond"
        elif "dubbel" in cleaned or "bruin" in cleaned:
            alias_key = "brugse zot dubbel"
    elif norm_brewery == "rochefort":
        for num in ["10", "8", "6"]:
            if re.search(rf"\b{num}\b", cleaned):
                alias_key = f"trappistes {num}"
                break
        if "triple extra" in cleaned:
            alias_key = "triple extra"
    elif norm_brewery == "la trappe":
        for style in ["quadrupel", "tripel", "dubbel", "blond", "isid", "witte", "bock"]:
            if style in cleaned:
                alias_key = "isidor" if style == "isid" else style
                break
    elif norm_brewery == "orval":
        alias_key = "trappist ale"
    elif norm_brewery == "pilsner urquell":
        alias_key = "pilsner"
    elif norm_brewery == "bitburger":
        if "0 0" in cleaned or "zero" in cleaned or "sem alcool" in cleaned:
            alias_key = "drive 0.0"
        else:
            alias_key = "premium pils"
    elif norm_brewery == "hofbrau":
        if "original" in cleaned or "hell" in cleaned:
            alias_key = "original"
        elif "weisse" in cleaned or "weiss" in cleaned:
            alias_key = "munchner weisse"
        elif "dunkel" in cleaned:
            alias_key = "dunkel"
        elif "oktoberfest" in cleaned:
            alias_key = "oktoberfestbier"
    elif norm_brewery == "hacker-pschorr":
        if "gold" in cleaned:
            alias_key = "munchner gold"
        elif "weiss" in cleaned or "weisse" in cleaned:
            alias_key = "hefe weisse"
        elif "keller" in cleaned:
            alias_key = "kellerbier"

    if not alias_key:
        alias_key = "classica"

    slug = re.sub(r"[^a-z0-9]+", "-", f"{norm_brewery}-{alias_key}").strip("-")
    display_name = f"{brewery} {alias_key.title()}"
    return slug, display_name
