from __future__ import annotations

"""Motor analitico da avaliacao Discente -> Docente.

A fonte SEI preserva respostas categoricas. Este modulo nao converte essas
respostas para uma nota 0-10. A unica derivacao sintetica e a favorabilidade,
calculada por um mapa explicito de categorias e sempre acompanhada do
respectivo denominador.
"""

from collections import defaultdict
from typing import Iterable

from survey_parser import normalize_key


FAVORABLE_KEYS = {
    "sempre",
    "quase sempre",
    "otimo",
    "otima",
    "bom",
    "boa",
    "excelente",
    "muito boa",
    "muito bom",
}
INTERMEDIATE_KEYS = {
    "regular",
    "razoavel",
}
UNFAVORABLE_KEYS = {
    "quase nunca",
    "nunca",
    "insuficiente",
}
UNCLASSIFIED_KEYS = {
    "nao sei",
    "nao sei responder",
    "nao se aplica",
    "nao aplicavel",
}

SCALE_FREQUENCY_KEYS = {"sempre", "quase sempre", "quase nunca", "nunca"}
SCALE_QUALITY_KEYS = {"otimo", "otima", "bom", "boa", "regular", "insuficiente"}
SCALE_EXCELLENCE_KEYS = {"excelente", "muito boa", "muito bom", "razoavel", "insuficiente"}



def classify_faculty_question(text: str | None) -> str:
    """Separa perguntas sobre o docente de itens contextuais/institucionais.

    O questionario real observado possui oito itens que citam explicitamente
    professor/docente e um nono item sobre o UNIVC EAD. O item contextual e
    preservado na API, mas nao compoe a favorabilidade sintetica do professor.
    """

    key = normalize_key(text or "")
    tokens = set(key.split())
    return "teacher" if {"professor", "docente"} & tokens else "contextual"

def classify_faculty_option(label: str | None) -> str:
    key = normalize_key(label or "")
    if key in FAVORABLE_KEYS:
        return "favorable"
    if key in INTERMEDIATE_KEYS:
        return "intermediate"
    if key in UNFAVORABLE_KEYS:
        return "unfavorable"
    if key in UNCLASSIFIED_KEYS:
        return "unclassified"
    return "unmapped"


def detect_faculty_scale(labels: Iterable[str]) -> str:
    keys = {normalize_key(label) for label in labels if normalize_key(label)}
    classified = keys - UNCLASSIFIED_KEYS
    if classified and classified <= SCALE_FREQUENCY_KEYS:
        return "frequency"
    if classified and classified <= SCALE_QUALITY_KEYS:
        return "quality"
    if classified and classified <= SCALE_EXCELLENCE_KEYS:
        return "excellence"
    return "categorical"


def favorability_summary(rows: Iterable[dict]) -> dict:
    """Resume distribuicoes sem alterar as contagens originais.

    ``classified_total`` e o denominador dos percentuais favoravel/intermediario/
    desfavoravel. Respostas desconhecidas/nao aplicaveis ficam em
    ``unclassified_total`` e categorias futuras nao mapeadas em ``unmapped_total``.
    """

    buckets = defaultdict(int)
    source_total = 0
    labels: list[str] = []
    for row in rows:
        label = str(row.get("option_label") or row.get("label") or "")
        count = max(0, int(row.get("response_count", row.get("count", 0)) or 0))
        labels.append(label)
        source_total += count
        buckets[classify_faculty_option(label)] += count

    classified_total = buckets["favorable"] + buckets["intermediate"] + buckets["unfavorable"]

    def pct(value: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round(value / denominator * 100.0, 2)

    mapping_complete = buckets["unmapped"] == 0
    return {
        "scale": detect_faculty_scale(labels),
        "mapping_complete": mapping_complete,
        "source_total": source_total,
        "classified_total": classified_total,
        "favorable": buckets["favorable"],
        "intermediate": buckets["intermediate"],
        "unfavorable": buckets["unfavorable"],
        "unclassified_total": buckets["unclassified"],
        "unmapped_total": buckets["unmapped"],
        "favorable_percentage": pct(buckets["favorable"], classified_total) if mapping_complete else None,
        "intermediate_percentage": pct(buckets["intermediate"], classified_total) if mapping_complete else None,
        "unfavorable_percentage": pct(buckets["unfavorable"], classified_total) if mapping_complete else None,
        "classified_coverage_percentage": pct(classified_total, source_total),
    }


def distribution_with_classification(rows: Iterable[dict]) -> dict:
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        label = str(row.get("option_label") or row.get("label") or "")
        key = normalize_key(label)
        count = max(0, int(row.get("response_count", row.get("count", 0)) or 0))
        if key not in grouped:
            grouped[key] = {"label": label, "count": 0}
            order.append(key)
        grouped[key]["count"] += count

    total = sum(item["count"] for item in grouped.values())
    items = []
    for key in order:
        item = grouped[key]
        count = item["count"]
        items.append({
            "label": item["label"],
            "count": count,
            "percentage": round(count / total * 100.0, 2) if total else 0.0,
            "classification": classify_faculty_option(item["label"]),
        })
    return {"total": total, "items": items}


def faculty_favorability_methodology() -> dict:
    return {
        "indicator": "favorability",
        "is_source_score": False,
        "description": (
            "Indicador derivado pelo Data UNIVC a partir das categorias originais do SEI. "
            "Nao representa nota 0-10 nem altera a distribuicao da fonte."
        ),
        "denominator": (
            "Somente respostas classificadas como favoraveis, intermediarias ou desfavoraveis. "
            "'Nao sei', 'Nao sei responder' e equivalentes ficam fora do denominador. "
            "Se surgir uma categoria ainda nao mapeada, os percentuais sinteticos ficam indisponiveis ate revisao."
        ),
        "question_scope": {
            "teacher": "Perguntas que citam explicitamente professor ou docente; compoem a favorabilidade sintetica.",
            "contextual": "Perguntas contextuais/institucionais permanecem visiveis, mas nao compoem a favorabilidade do docente.",
        },
        "classification": {
            "favorable": sorted(FAVORABLE_KEYS),
            "intermediate": sorted(INTERMEDIATE_KEYS),
            "unfavorable": sorted(UNFAVORABLE_KEYS),
            "unclassified": sorted(UNCLASSIFIED_KEYS),
        },
    }
