import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _average_word_length(words: list[str]) -> float:
    if not words:
        return 0.0
    return sum(len(word) for word in words) / len(words)


def _score_from_metrics(
    type_token_ratio: float,
    hapax_ratio: float,
    word_count: int,
    average_word_length: float,
) -> float:
    if word_count < 25:
        return 0.50

    if type_token_ratio > 0.70:
        base_score = round(0.20 + (1.0 - type_token_ratio) * 0.50, 2)
    elif 0.35 <= type_token_ratio <= 0.55 and hapax_ratio < 0.25:
        midpoint = 0.45
        distance = abs(type_token_ratio - midpoint) / 0.10
        base_score = round(0.85 - distance * 0.10, 2)
    elif type_token_ratio < 0.35:
        base_score = round(0.55 + (0.35 - type_token_ratio) * 0.50, 2)
    else:
        base_score = 0.50

    if (
        word_count < 60
        and average_word_length >= 5.5
        and 0.55 <= type_token_ratio <= 0.90
        and hapax_ratio >= 0.55
    ):
        base_score = max(base_score, 0.68)

    if word_count < 50:
        weight = (word_count - 25) / 25
        return round(0.50 * (1 - weight) + base_score * weight, 2)

    return base_score


def analyze_lexical_diversity(text: str) -> dict:
    words = _tokenize(text)
    word_count = len(words)

    if word_count == 0:
        return {
            "name": "lexical_diversity",
            "score": 0.50,
            "details": {
                "type_token_ratio": 0.0,
                "hapax_ratio": 0.0,
                "word_count": 0,
            },
        }

    counts = Counter(words)
    unique_count = len(counts)
    hapax_count = sum(1 for count in counts.values() if count == 1)

    type_token_ratio = round(unique_count / word_count, 4)
    hapax_ratio = round(hapax_count / word_count, 4)
    average_word_length = round(_average_word_length(words), 4)
    score = _score_from_metrics(
        type_token_ratio,
        hapax_ratio,
        word_count,
        average_word_length,
    )

    return {
        "name": "lexical_diversity",
        "score": score,
        "details": {
            "type_token_ratio": type_token_ratio,
            "hapax_ratio": hapax_ratio,
            "word_count": word_count,
            "average_word_length": average_word_length,
        },
    }
