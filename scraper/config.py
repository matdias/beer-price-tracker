MIN_DROP_PERCENT = 10.0  # Queda mínima (%) sobre o menor R$/L histórico do grupo para disparar alerta

BREWERIES = {
    "Schlenkerla": ["schlenkerla"],
    "Duvel": ["duvel"],
    "Paulaner": ["paulaner"],
    "Bitburger": ["bitburger"],
    "De Halve Maan": ["halve maan", "straffe hendrik", "brugse zot", "brugs zot"],
    "Hacker-Pschorr": ["hacker pschorr", "hacker-pschorr"],
    "Hofbräu": ["hofbrau", "hofbräu"],
    "Pilsner Urquell": ["pilsner urquell", "urquell"],
    "Orval": ["orval"],
    "Rochefort": ["rochefort"],
    "La Trappe": ["la trappe"],
}

NEGATIVE_KEYWORDS = [
    # Copos, taças e kits promocionais com brinde/souvenir
    "taça", "taca", "taças", "tacas",
    "cálice", "calice", "cálices", "calices",
    "copo", "copos", "caneca", "canecas",
    "com copo", "c/ copo", "com taça", "c/ taça", "com taca", "c/ taca",
    "com cálice", "c/ cálice", "com calice", "c/ calice",
    "com caneca", "c/ caneca", "copo exclusivo", "taça exclusiva",
    "bolacha", "porta copo", "porta-copo", "camiseta", "boné", "bone",
    "quadro", "placa", "balde", "abridor", "chaveiro", "cooler",
    "adesivo", "bandeira", "souvenir", "gift", "presente",
    # Insumos de brewshop
    "insumo", "malte", "lúpulo", "lupulo", "levedura", "fermento",
    "receita 20l", "receita 10l", "receita 40l", "extrato de malte",
    "post mix", "post-mix", "keg vazio"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
