import re
import statistics


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+", text)
    return [part.strip() for part in parts if part.strip()]


def _sentence_word_count(sentence: str) -> int:
    return len(re.findall(r"[a-zA-Z']+", sentence))


def _score_from_cv(
    coefficient_of_variation: float,
    sentence_count: int,
    lengths: list[int],
) -> float:
    if sentence_count < 3:
        return 0.50

    if sentence_count < 4:
        average_length = statistics.mean(lengths)
        length_ratio = max(lengths) / min(lengths) if min(lengths) else 1.0
        if 10 <= average_length <= 24 and length_ratio <= 2.5:
            return 0.72

    if coefficient_of_variation < 0.25:
        return round(0.95 - (coefficient_of_variation / 0.25) * 0.15, 2)

    if coefficient_of_variation <= 0.45:
        progress = (coefficient_of_variation - 0.25) / 0.20
        return round(0.70 - progress * 0.25, 2)

    capped_cv = min(coefficient_of_variation, 0.80)
    progress = (capped_cv - 0.45) / 0.35
    return round(0.35 - progress * 0.20, 2)


def analyze_burstiness(text: str) -> dict:
    sentences = _split_sentences(text)
    sentence_count = len(sentences)

    if sentence_count == 0:
        return {
            "name": "burstiness",
            "score": 0.50,
            "details": {
                "sentence_count": 0,
                "average_sentence_length": 0.0,
                "sentence_length_stdev": 0.0,
                "coefficient_of_variation": 0.0,
            },
        }

    lengths = [_sentence_word_count(sentence) for sentence in sentences]
    average_sentence_length = round(statistics.mean(lengths), 4)

    if sentence_count == 1:
        stdev = 0.0
        coefficient_of_variation = 0.0
    else:
        stdev = round(statistics.stdev(lengths), 4)
        coefficient_of_variation = round(stdev / average_sentence_length, 4) if average_sentence_length else 0.0

    score = _score_from_cv(coefficient_of_variation, sentence_count, lengths)

    return {
        "name": "burstiness",
        "score": score,
        "details": {
            "sentence_count": sentence_count,
            "average_sentence_length": average_sentence_length,
            "sentence_length_stdev": stdev,
            "coefficient_of_variation": coefficient_of_variation,
        },
    }
