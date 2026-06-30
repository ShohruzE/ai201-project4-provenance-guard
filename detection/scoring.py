LEXICAL_WEIGHT = 0.40
BURSTINESS_WEIGHT = 0.60


def combine_signals(lexical_score: float, burstiness_score: float) -> tuple[float, float]:
    full_precision = (lexical_score * LEXICAL_WEIGHT) + (burstiness_score * BURSTINESS_WEIGHT)
    rounded = round(full_precision, 2)
    return rounded, full_precision


def attribution_from_score(score: float) -> str:
    if score >= 0.85:
        return "likely_ai"
    if score <= 0.30:
        return "likely_human"
    return "uncertain"


def generate_label(attribution: str, confidence: float) -> str:
    score_percent = round(confidence * 100)

    if attribution == "likely_ai":
        return (
            f"Provenance Guard found strong signs that this content may have been AI-generated. "
            f"AI-likelihood: {score_percent}%. The creator can appeal this label if they believe it is wrong."
        )

    if attribution == "likely_human":
        human_percent = round((1 - confidence) * 100)
        return (
            f"Provenance Guard found strong signs that this content was written by a human. "
            f"Human-likelihood: {human_percent}%. No major AI-generation patterns were detected."
        )

    return (
        f"Provenance Guard could not confidently determine the origin of this content. "
        f"AI-likelihood: {score_percent}%. This label means the evidence is mixed, "
        f"and the creator can request review."
    )
