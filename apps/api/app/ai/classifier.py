"""Clasificador de texto de casos "otro" (regla técnica PRD §18: nunca escribe en ledgers).

Interfaz estable para integrar un modelo real más adelante:

    classify_help_text(text: str) -> {"category": str, "confidence": float, "model_version": str}

- `category` ∈ {"cart", "battery", "product", "payment", "security", "other"}
- `confidence` ∈ [0, 1]
- `model_version`: identificador trazable del modelo/reglas usadas.

Implementación MVP: reglas por palabras clave (determinístico, sin red). El resultado se
persiste como `AIRecommendation` y el humano conserva la capacidad de corregir la categoría.
"""
import re
import unicodedata

MODEL_VERSION = "keyword-rules-v1"

KEYWORDS: dict[str, list[str]] = {
    "battery": ["bateria", "pila", "carga", "cargador", "se apago", "sin energia", "energia", "descargado"],
    "cart": ["carrito", "llanta", "rueda", "freno", "toldo", "sombrilla", "candado", "chapa", "cajon", "vitrina"],
    "product": ["pepita", "pepitas", "producto", "bolsa", "bolsas", "caduc", "mojado", "rancio", "sabor", "semilla"],
    "payment": ["cobro", "cobrar", "terminal", "pos", "tarjeta", "qr", "pago", "cambio", "efectivo", "transferencia"],
    "security": ["robo", "asalto", "roban", "robaron", "amenaza", "pelea", "golpe", "policia", "seguridad", "peligro", "arma"],
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def classify_help_text(text: str) -> dict:
    norm = _normalize(text)
    if not norm:
        return {"category": "other", "confidence": 0.0, "model_version": MODEL_VERSION}
    scores: dict[str, int] = {}
    for category, words in KEYWORDS.items():
        hits = sum(1 for w in words if w in norm)
        if hits:
            scores[category] = hits
    if not scores:
        return {"category": "other", "confidence": 0.2, "model_version": MODEL_VERSION}
    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    # Confianza: proporción de coincidencias de la mejor categoría, saturando con más evidencia.
    confidence = min(0.95, 0.5 + 0.45 * (scores[best] / total) * min(1.0, scores[best] / 2))
    return {"category": best, "confidence": round(confidence, 2), "model_version": MODEL_VERSION}
