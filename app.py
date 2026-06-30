import hashlib
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit import append_entry, get_log, utc_now_iso
from detection.burstiness import analyze_burstiness
from detection.lexical import analyze_lexical_diversity
from detection.scoring import attribution_from_score, combine_signals, generate_label
from storage import get_submission, save_submission, update_submission

MIN_TEXT_LENGTH = 50
MAX_TEXT_LENGTH = 10000
MIN_APPEAL_REASONING_LENGTH = 20
MAX_APPEAL_REASONING_LENGTH = 2000

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


def _extract_text(payload: dict) -> str | None:
    text = payload.get("text")
    if text is None:
        text = payload.get("content")
    if text is None:
        return None
    return str(text).strip()


def _extract_appeal_reasoning(payload: dict) -> str | None:
    reasoning = payload.get("creator_reasoning")
    if reasoning is None:
        reasoning = payload.get("reasoning")
    if reasoning is None:
        return None
    return str(reasoning).strip()


def _content_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _log_classification(
    content_id: str,
    creator_id: str,
    text: str,
    attribution: str,
    confidence: float,
    confidence_full: float,
    lexical_score: float,
    burstiness_score: float,
    label: str,
    timestamp: str,
) -> None:
    append_entry(
        {
            "entry_id": str(uuid.uuid4()),
            "event_type": "classification",
            "content_id": content_id,
            "creator_id": creator_id,
            "timestamp": timestamp,
            "attribution": attribution,
            "confidence": confidence_full,
            "lexical_score": lexical_score,
            "burstiness_score": burstiness_score,
            "label": label,
            "content_hash": _content_hash(text),
            "status": "classified",
            "appeal_filed": False,
        }
    )


@app.post("/submit")
@limiter.limit("10 per minute;50 per hour")
def submit():
    payload = request.get_json(silent=True) or {}
    text = _extract_text(payload)
    creator_id = payload.get("creator_id")

    if not text:
        return jsonify({"error": "text is required"}), 400

    if creator_id is None or str(creator_id).strip() == "":
        return jsonify({"error": "creator_id is required"}), 400

    if len(text) < MIN_TEXT_LENGTH:
        return jsonify(
            {"error": f"text must be at least {MIN_TEXT_LENGTH} characters"}
        ), 400

    if len(text) > MAX_TEXT_LENGTH:
        return jsonify(
            {"error": f"text must be at most {MAX_TEXT_LENGTH} characters"}
        ), 400

    content_id = str(uuid.uuid4())
    timestamp = utc_now_iso()

    lexical = analyze_lexical_diversity(text)
    burstiness = analyze_burstiness(text)
    confidence, confidence_full = combine_signals(lexical["score"], burstiness["score"])
    attribution = attribution_from_score(confidence)
    label = generate_label(attribution, confidence)

    response = {
        "content_id": content_id,
        "creator_id": str(creator_id),
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "lexical_diversity": lexical,
            "burstiness": burstiness,
        },
        "status": "classified",
        "timestamp": timestamp,
    }

    save_submission(content_id, response)
    _log_classification(
        content_id=content_id,
        creator_id=str(creator_id),
        text=text,
        attribution=attribution,
        confidence=confidence,
        confidence_full=confidence_full,
        lexical_score=lexical["score"],
        burstiness_score=burstiness["score"],
        label=label,
        timestamp=timestamp,
    )

    return jsonify(response), 200


@app.post("/appeal")
@limiter.limit("3 per hour")
def appeal():
    payload = request.get_json(silent=True) or {}
    content_id = payload.get("content_id") or payload.get("submission_id")
    creator_reasoning = _extract_appeal_reasoning(payload)
    creator_id = payload.get("creator_id")

    if not content_id:
        return jsonify({"error": "content_id is required"}), 400

    if not creator_reasoning:
        return jsonify({"error": "creator_reasoning is required"}), 400

    if len(creator_reasoning) < MIN_APPEAL_REASONING_LENGTH:
        return jsonify(
            {
                "error": (
                    f"creator_reasoning must be at least "
                    f"{MIN_APPEAL_REASONING_LENGTH} characters"
                )
            }
        ), 400

    if len(creator_reasoning) > MAX_APPEAL_REASONING_LENGTH:
        return jsonify(
            {
                "error": (
                    f"creator_reasoning must be at most "
                    f"{MAX_APPEAL_REASONING_LENGTH} characters"
                )
            }
        ), 400

    submission = get_submission(str(content_id))
    if submission is None:
        return jsonify({"error": "submission not found"}), 404

    if creator_id is not None and str(creator_id) != submission.get("creator_id"):
        return jsonify({"error": "creator_id does not match this submission"}), 403

    if submission.get("status") == "under_review":
        return jsonify({"error": "an appeal is already under review for this submission"}), 409

    appeal_id = str(uuid.uuid4())
    timestamp = utc_now_iso()

    update_submission(
        str(content_id),
        {
            "status": "under_review",
            "appeal": {
                "appeal_id": appeal_id,
                "creator_reasoning": creator_reasoning,
                "submitted_at": timestamp,
            },
        },
    )

    append_entry(
        {
            "entry_id": str(uuid.uuid4()),
            "event_type": "appeal",
            "appeal_id": appeal_id,
            "content_id": str(content_id),
            "creator_id": submission.get("creator_id"),
            "timestamp": timestamp,
            "status": "under_review",
            "appeal_reasoning": creator_reasoning,
            "original_attribution": submission.get("attribution"),
            "original_confidence": submission.get("confidence"),
            "original_label": submission.get("label"),
            "lexical_score": submission.get("signals", {})
            .get("lexical_diversity", {})
            .get("score"),
            "burstiness_score": submission.get("signals", {})
            .get("burstiness", {})
            .get("score"),
        }
    )

    return jsonify(
        {
            "appeal_id": appeal_id,
            "content_id": str(content_id),
            "status": "under_review",
            "message": (
                "Your appeal has been received. This submission is now marked for human review."
            ),
            "timestamp": timestamp,
        }
    ), 200


@app.get("/log")
def log():
    return jsonify({"entries": get_log()}), 200


@app.get("/")
def home():
    return jsonify({"message": "Welcome to Provenance Guard"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
