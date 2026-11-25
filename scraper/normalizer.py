import re
import unicodedata
from typing import Optional, Tuple
from .config import BREWERIES, NEGATIVE_KEYWORDS


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
    return re.sub(r"\s+", " ", text.lower()).strip()


def is_valid_beer(title: str, expected_brewery: str) -> bool:
    norm = normalize_text(title)
    if not norm:
        return False

    # 1. Filtro Negativo
    for bad_word in NEGATIVE_KEYWORDS:
        norm_bad = normalize_text(bad_word)
        if re.search(rf"\b{re.escape(norm_bad)}s?\b", norm):
            return False

    # 2. Garante que o título contém algum termo da cervejaria esperada
    terms = BREWERIES.get(expected_brewery, [])
    return any(normalize_text(t) in norm for t in terms)


def extract_volume_and_qty(title: str) -> Tuple[Optional[int], int]:
    """
    Retorna (volume_unitario_ml, quantidade_unidades).
    Ex: 'Cerveja Paulaner Weissbier 500ml Kit com 4' -> (500, 4)
    Ex: 'Barril Paulaner 5L' -> (5000, 1)
    """
    norm = normalize_text(title)

    # Extração de volume unitário
    vol_ml: Optional[int] = None
    ml_match = re.search(r"(\d{2,4})\s*ml\b", norm)
    l_match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:l|litros?)\b", norm)

    if ml_match:
        vol_ml = int(ml_match.group(1))
    elif l_match:
        liters = float(l_match.group(1).replace(",", "."))
        # Evita confundir "receita 20l" caso escape, focando em embalagens reais (até 30L)
        if liters <= 30:
            vol_ml = int(round(liters * 1000))

    # Extração de quantidade (kits, packs, caixas, combos 4+1)
    qty = 1

    # Caso especial: "4+1", "3+1", "5+1"
    plus_match = re.search(r"\b(\d+)\s*\+\s*(\d+)\b", norm)
    if plus_match:
        a, b = int(plus_match.group(1)), int(plus_match.group(2))
        if 1 <= a <= 24 and 1 <= b <= 12:
            qty = a + b
            return vol_ml, qty

    # Padrões explícitos de pack/kit/caixa/unidades
    qty_patterns = [
        r"(?:kit|pack|caixa|cx|fardo|combo)\s*(?:com|c/|de)?\s*(\d{1,2})\b",
        r"\bc/\s*(\d{1,2})\b",
        r"\b(\d{1,2})\s*(?:unidades|unid|uns|garrafas|latas|long necks)\b",
    ]
    for pat in qty_patterns:
        m = re.search(pat, norm)
        if m:
            found = int(m.group(1))
            if 2 <= found <= 36:
                qty = found
                break

    return vol_ml, qty


def parse_price_brl(raw_price) -> Optional[float]:
    if raw_price is None:
        return None
    if isinstance(raw_price, (int, float)):
        val = float(raw_price)
        return round(val, 2) if val > 0 else None

    cleaned = re.sub(r"[^\d,.]", "", str(raw_price))
    if not cleaned:
        return None

    # Formato brasileiro: 1.234,56 -> 1234.56
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    try:
        val = float(cleaned)
        return round(val, 2) if val > 0 else None
    except ValueError:
        return None


def calculate_price_per_liter(price: float, vol_ml: Optional[int], qty: int) -> Optional[float]:
    if not price or not vol_ml or vol_ml <= 0:
        return None
    total_liters = (vol_ml * qty) / 1000.0
    return round(price / total_liters, 2)
