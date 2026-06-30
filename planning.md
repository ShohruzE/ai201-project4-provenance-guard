# Provenance Guard Planning Document

## Project Goal

Provenance Guard will be a small Flask backend that helps a creative writing platform explain whether a submitted text looks human-written, AI-generated, or too uncertain to label strongly. The goal is not to punish creators. The system should give readers useful context, avoid careless accusations, and give creators a clear appeal path.

The first version will handle text only, such as poems, short stories, blog posts, and essays. Stretch features are not planned yet.

## Architecture

```text
Submission flow

Client
  |
  | POST /submit with raw text, creator_id, content_type
  v
Rate limiter
  |
  | allowed request
  v
Input validator
  |
  | cleaned text
  v
Detection pipeline
  |
  | text
  +--> Signal 1: lexical diversity -> lexical_ai_score 0.0 to 1.0
  |
  +--> Signal 2: sentence burstiness -> burstiness_ai_score 0.0 to 1.0
  |
  v
Confidence scorer
  |
  | combined_ai_score 0.0 to 1.0
  v
Label generator
  |
  | classification and exact label text
  v
Audit logger and in-memory store
  |
  | saved decision record
  v
JSON response to client


Appeal flow

Creator
  |
  | POST /appeal with submission_id, creator_id, reasoning
  v
Input validator
  |
  | valid appeal
  v
Submission lookup
  |
  | original decision found
  v
Status update to under_review
  |
  | appeal plus original decision
  v
Audit logger
  |
  | appeal record saved
  v
JSON confirmation to creator
```

When text is submitted, the API validates it, runs two independent detection signals, combines their outputs into one AI-likelihood score, generates a reader-facing label, and logs the full decision. If a creator appeals, the system does not automatically reclassify the work. It marks the submission as `under_review`, stores the creator's explanation, and logs the appeal next to the original decision.

## API Plan

### `POST /submit`

Accepts:

```json
{
  "content": "string, required, 50 to 10000 characters",
  "creator_id": "string, optional",
  "content_type": "poem | story | blog | essay | general, optional"
}
```

Returns:

```json
{
  "submission_id": "uuid",
  "classification": "likely_ai | likely_human | uncertain",
  "confidence_score": 0.87,
  "signals": {
    "lexical_diversity": {
      "score": 0.82,
      "details": {
        "type_token_ratio": 0.41,
        "hapax_ratio": 0.18
      }
    },
    "burstiness": {
      "score": 0.90,
      "details": {
        "average_sentence_length": 18.4,
        "sentence_length_stdev": 3.1
      }
    }
  },
  "transparency_label": "exact label text",
  "status": "classified",
  "timestamp": "ISO 8601"
}
```

### `POST /appeal`

Accepts:

```json
{
  "submission_id": "uuid, required",
  "creator_id": "string, required",
  "reasoning": "string, required, 20 to 2000 characters"
}
```

Returns:

```json
{
  "appeal_id": "uuid",
  "submission_id": "uuid",
  "status": "under_review",
  "message": "Your appeal has been received. This submission is now marked for human review.",
  "timestamp": "ISO 8601"
}
```

### `GET /audit-log`

Returns recent classification and appeal events. Each entry should include the event type, submission ID, timestamp, score, signals, label, and appeal reasoning when present.

## Detection Signals

### Signal 1: Lexical Diversity

This signal measures how varied the word choices are. It uses type-token ratio, which is unique words divided by total words, and hapax ratio, which is the share of words that appear only once.

Output format:

```json
{
  "name": "lexical_diversity",
  "score": 0.0,
  "details": {
    "type_token_ratio": 0.0,
    "hapax_ratio": 0.0,
    "word_count": 0
  }
}
```

The score is an AI-likelihood score from 0.0 to 1.0. A higher score means the vocabulary pattern looks more AI-like. For the first implementation, I will use these rough rules:

- If word count is under 50, return `score: 0.50` because there is not enough text.
- If type-token ratio is between `0.35` and `0.55` and hapax ratio is below `0.25`, return a higher AI score around `0.70` to `0.85`.
- If type-token ratio is very high, above `0.70`, return a lower AI score around `0.20` to `0.35`.
- If the values fall in the middle, return around `0.50`.

This helps because AI writing often has smooth, safe vocabulary. It can miss minimalist human writers, non-native English writers, technical writing with repeated terms, and very short poems.

### Signal 2: Sentence Burstiness

This signal measures whether sentence lengths vary naturally. It calculates average sentence length, standard deviation, and coefficient of variation.

Output format:

```json
{
  "name": "burstiness",
  "score": 0.0,
  "details": {
    "sentence_count": 0,
    "average_sentence_length": 0.0,
    "sentence_length_stdev": 0.0,
    "coefficient_of_variation": 0.0
  }
}
```

The score is also an AI-likelihood score from 0.0 to 1.0. A higher score means the sentence rhythm looks more AI-like. For the first implementation, I will use these rough rules:

- If there are fewer than 4 sentences, return `score: 0.50`.
- If coefficient of variation is below `0.25`, return `0.80` to `0.95` because the sentences are very uniform.
- If coefficient of variation is between `0.25` and `0.45`, return `0.45` to `0.70`.
- If coefficient of variation is above `0.45`, return `0.15` to `0.35` because the rhythm is more varied.

This helps because human writing often mixes short, medium, and long sentences. It can struggle with poetry, academic writing, bullet-heavy posts, and AI text that was prompted to vary its rhythm.

### Combining the Signals

Both signals return an AI-likelihood score from `0.0` to `1.0`. The combined score will use a weighted average:

```text
combined_ai_score = (lexical_score * 0.40) + (burstiness_score * 0.60)
```

Burstiness gets slightly more weight because sentence rhythm is harder to fake accidentally and works better for creative writing than vocabulary alone. The API will round the final score to two decimals for output, while keeping full precision inside the audit log.

## Uncertainty Representation

The confidence score means "how strongly the system thinks the content looks AI-generated." It is not a perfect probability. A score of `0.60` means the signals lean toward AI, but the system should not present that as a firm claim.

Raw signal outputs are calibrated into the `0.0` to `1.0` range before they are combined. A score near `0.0` means strong human indicators, a score near `0.5` means weak or mixed evidence, and a score near `1.0` means strong AI indicators.

The label thresholds will be:

- `0.00` to `0.30`: `likely_human`
- `0.31` to `0.84`: `uncertain`
- `0.85` to `1.00`: `likely_ai`

The AI threshold is intentionally high because a false positive can hurt a creator's reputation. A score of `0.51` and a score of `0.84` are both uncertain, but the label can still show the numeric AI-likelihood so readers understand the difference.

## Transparency Label Design

High-confidence AI result, used when `combined_ai_score >= 0.85`:

> "Provenance Guard found strong signs that this content may have been AI-generated. AI-likelihood: {score}%. The creator can appeal this label if they believe it is wrong."

High-confidence human result, used when `combined_ai_score <= 0.30`:

> "Provenance Guard found strong signs that this content was written by a human. Human-likelihood: {human_score}%. No major AI-generation patterns were detected."

Uncertain result, used when `0.30 < combined_ai_score < 0.85`:

> "Provenance Guard could not confidently determine the origin of this content. AI-likelihood: {score}%. This label means the evidence is mixed, and the creator can request review."

Before implementation, I should review these exact strings again and copy them into the README so the required label variants match the backend output.

## Appeals Workflow

Only the creator attached to a submission can submit an appeal. For this class project, that means the appeal request must include the same `creator_id` that was used on the original submission.

The creator provides:

- `submission_id`
- `creator_id`
- a written explanation between 20 and 2000 characters

When the appeal is received, the system will:

- check that the submission exists
- check that the creator ID matches the submission
- create an `appeal_id`
- change the submission status from `classified` to `under_review`
- store the appeal reasoning with the original classification, confidence score, signal details, and label text
- add an audit log event with `event_type: "appeal"`

A human reviewer opening the appeal queue would see the submission ID, creator ID, current status, original text preview, original label, combined score, both signal outputs, timestamp, and the creator's appeal reasoning. The reviewer would not need to guess why the system made the decision because the signal details would be visible.

## Anticipated Edge Cases

A short poem with repeated simple lines may look AI-generated because lexical diversity is low and sentence rhythm is repetitive. For example, a poem that repeats "I waited by the door" could be original human work but still score high on both signals.

A technical blog post may reuse the same domain words many times. A human-written post about neural networks, climate modeling, or chemistry could have low vocabulary variety because the topic requires repeated terms.

A polished college essay may have even sentence lengths after editing. If the writer revised it carefully, the burstiness signal may treat the smooth structure as AI-like.

An AI text prompted to include fragments, slang, and uneven pacing may score more human than it should. The system should still log the signal details so the weakness is visible.

## Rate Limiting and Audit Log Plan

The `POST /submit` endpoint will allow `10 per minute` and `50 per hour` per IP address. This is enough for normal creators but slows down someone trying to test hundreds of tiny prompt changes.

The `POST /appeal` endpoint will allow `3 per hour` per IP address. Appeals should be rare and thoughtful, so this still gives a creator room to contest multiple decisions.

Each classification audit entry will include:

```json
{
  "event_type": "classification",
  "submission_id": "uuid",
  "timestamp": "ISO 8601",
  "content_hash": "sha256 hash",
  "classification": "likely_ai | likely_human | uncertain",
  "confidence_score": 0.87,
  "signals": {},
  "label": "exact label text"
}
```

Each appeal audit entry will include:

```json
{
  "event_type": "appeal",
  "appeal_id": "uuid",
  "submission_id": "uuid",
  "timestamp": "ISO 8601",
  "previous_status": "classified",
  "new_status": "under_review",
  "reasoning": "creator explanation"
}
```

## AI Tool Plan

### M3: Submission Endpoint and First Signal

I will give the AI tool the `Architecture`, `API Plan`, and `Detection Signals` sections. I will ask it to generate a Flask app skeleton with `POST /submit`, request validation, in-memory submission storage, and the lexical diversity signal function.

I will verify the output by calling the lexical diversity function directly with a short repeated text, a varied human-style paragraph, and a smooth AI-style paragraph. I will check that the function returns the required JSON shape and that the score changes instead of staying fixed.

### M4: Second Signal and Confidence Scoring

I will give the AI tool the `Architecture`, `Detection Signals`, and `Uncertainty Representation` sections. I will ask it to add the sentence burstiness function and the weighted scoring logic.

I will verify this milestone by testing clearly uniform text, clearly varied text, and a mixed example. The scores should move across the range, and at least one test should reach each general area: likely human, uncertain, and likely AI.

### M5: Production Layer

I will give the AI tool the `Architecture`, `Transparency Label Design`, `Appeals Workflow`, and `Rate Limiting and Audit Log Plan` sections. I will ask it to add label generation, the `POST /appeal` endpoint, rate limiting, and structured audit logging.

I will verify this milestone by forcing scores that hit all three label variants, submitting an appeal for a real submission ID, checking that the status becomes `under_review`, and confirming that the audit log contains both the original classification and the appeal.

## Planned File Structure

```text
provenance-guard/
  app.py
  detection/
    __init__.py
    lexical.py
    burstiness.py
    scoring.py
  storage.py
  audit.py
  planning.md
  README.md
  requirements.txt
```
