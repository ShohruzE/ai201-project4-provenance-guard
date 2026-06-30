# Provenance Guard

A backend system that creative sharing platforms can plug into to classify submitted text, score confidence in that classification, show transparency labels to readers, and handle appeals from creators who believe they were misclassified.

The goal is not to police creativity. The system should give audiences useful context, avoid careless accusations, and give creators a clear path to contest a decision.

---

## Architecture

```text
Submission flow

Client
  |
  | POST /submit with text, creator_id
  v
Rate limiter -> Input validator -> Detection pipeline
  |
  +--> Signal 1: lexical diversity
  +--> Signal 2: sentence burstiness
  v
Confidence scorer -> Label generator -> Audit logger -> JSON response


Appeal flow

Creator
  |
  | POST /appeal with content_id, creator_reasoning
  v
Submission lookup -> Status update (under_review) -> Audit logger -> JSON response
```

A submission passes through rate limiting and validation, then two independent signals analyze the text. Their outputs are combined into one AI-likelihood score, mapped to a reader-facing label, and logged. Appeals do not trigger automatic re-classification. They mark the submission as `under_review` and store the creator's reasoning next to the original decision.

**Design choices:**
- **Two signals, not one:** A single heuristic is easy to game and hard to trust. Lexical diversity and burstiness measure different properties (vocabulary vs. rhythm), so disagreement between them is useful evidence of uncertainty.
- **Asymmetric thresholds:** Labeling a human as AI is more harmful than missing AI content on a creative platform, so the system requires stronger evidence (0.85+) before calling something AI-generated.
- **In-memory storage:** Fine for a class prototype. A real deployment would use a database and authenticated review tooling.

---

## Detection Signals

### Signal 1: Lexical Diversity

**What it measures:** Type-token ratio (unique words / total words) and hapax ratio (share of words that appear only once).

**Why these signals:** AI writing often lands in a safe middle vocabulary range. It avoids very rare words but also lacks the messy repetition patterns humans fall into. Human writers swing wider: poets reach for unusual words, bloggers repeat favorite phrases, and technical writers reuse domain terms. Lexical diversity captures that spread without needing an external model.

**Why not an LLM alone:** An LLM classifier is semantic and holistic, but it is slower, costs money per request, and is harder to audit. Stylometric heuristics are transparent: you can show exactly which metrics drove the score.

**Blind spots:** Short texts under ~50 words return a neutral score because there are not enough tokens. Non-native English writers may show constrained vocabulary. Formal AI text with rich vocabulary can look human on this signal alone.

### Signal 2: Sentence Burstiness

**What it measures:** Average sentence length, standard deviation, and coefficient of variation (stdev / mean) across all sentences.

**Why this signal:** Human writing is naturally uneven. A long sentence might be followed by a short punch. AI text, especially instruction-tuned output, tends toward uniform medium-length sentences. Burstiness captures rhythm, which is hard to fake with simple word swaps.

**Why it gets more weight (0.6 vs 0.4):** Sentence rhythm is a structural property. It is less genre-dependent than vocabulary alone and harder to manipulate accidentally.

**Blind spots:** Academic prose keeps sentences long and even on purpose. Poetry manipulates rhythm deliberately. AI prompted to vary sentence length can score more human than it should.

---

## Confidence Scoring

The confidence score is an **AI-likelihood score** from 0.0 to 1.0. It is not a statistical probability. It is a communication tool:

- **Near 0.0:** strong human indicators
- **Near 0.5:** mixed or weak evidence
- **Near 1.0:** strong AI indicators

### How scores are combined

```
combined_score = (0.4 × lexical_score) + (0.6 × burstiness_score)
```

### Classification thresholds

| Score range | Attribution | Why |
|-------------|-------------|-----|
| ≥ 0.85 | `likely_ai` | Strong evidence required before accusing |
| ≤ 0.30 | `likely_human` | Moderate evidence is enough to affirm human origin |
| 0.31 to 0.84 | `uncertain` | Wide band: the system says "I don't know" often |

### Example submissions (live test output)

**High-confidence human case:** casual, uneven writing with varied rhythm and informal vocabulary.

| Field | Value |
|-------|-------|
| Text | *"ok so i finally tried that new ramen place downtown and honestly? underwhelming..."* |
| Lexical score | 0.26 |
| Burstiness score | 0.23 |
| **Combined confidence** | **0.24** |
| Attribution | `likely_human` |

**High-confidence AI case:** repetitive vocabulary and perfectly uniform sentence lengths.

| Field | Value |
|-------|-------|
| Text | *"The results show that the results are clear and the results remain clear today..."* |
| Lexical score | 0.76 |
| Burstiness score | 0.95 |
| **Combined confidence** | **0.87** |
| Attribution | `likely_ai` |

These two cases differ by 0.63 points on the combined score and produce different labels. That gap is the evidence that scoring varies meaningfully rather than returning a constant.

### What I would change for a real deployment

- Calibrate thresholds on a labeled dataset instead of hand-tuned rules.
- Add a semantic signal (e.g., Groq) as a third input with documented weighting.
- Store per-signal explanations in the API response so reviewers can audit edge cases.
- Use persistent storage and signed audit logs.

---

## Transparency Labels

Exact text shown to readers for each variant:

### High-confidence AI (score ≥ 0.85)

> "Provenance Guard found strong signs that this content may have been AI-generated. AI-likelihood: {score}%. The creator can appeal this label if they believe it is wrong."

### High-confidence human (score ≤ 0.30)

> "Provenance Guard found strong signs that this content was written by a human. Human-likelihood: {human_score}%. No major AI-generation patterns were detected."

### Uncertain (0.30 < score < 0.85)

> "Provenance Guard could not confidently determine the origin of this content. AI-likelihood: {score}%. This label means the evidence is mixed, and the creator can request review."

Labels are written in plain language. Each one states the result, shows the confidence level as a percentage, and tells creators what they can do next.

---

## Appeals Workflow

1. Creator sends `POST /appeal` with `content_id` and `creator_reasoning` (20 to 2000 characters).
2. System finds the original submission.
3. Status changes from `classified` to `under_review`.
4. Audit log records the appeal next to the original classification.
5. Creator gets a confirmation response.

Appeals do **not** trigger automatic re-classification.

---

## Rate Limiting

| Endpoint | Limit | Reasoning |
|----------|-------|-----------|
| `POST /submit` | 10/minute, 50/hour per IP | Normal creators submit a few times per day. This blocks rapid probing without hurting real use. |
| `POST /appeal` | 3/hour per IP | Appeals should be rare and deliberate. |

**Rate limit test evidence** (12 rapid `POST /submit` requests):

```text
200 200 200 200 200 200 200 200 200 200 429 429
```

The first 10 requests succeeded. Requests 11 and 12 returned HTTP 429.

---

## Audit Log

Structured JSON via `GET /log`. Classification entries include timestamp, content ID, attribution, confidence, both signal scores, label text, and content hash. Appeal entries include `appeal_reasoning`, `status: under_review`, and the original decision.

### Sample (from live test run)

```json
[
  {
    "entry_id": "9bd9abf4-3049-48a2-a7a0-2b3d71c98e4b",
    "event_type": "classification",
    "content_id": "042ce62f-f93d-4006-a3dc-7871eb6927f5",
    "creator_id": "demo-1",
    "timestamp": "2026-06-30T18:21:39.996682Z",
    "attribution": "likely_human",
    "confidence": 0.242,
    "lexical_score": 0.26,
    "burstiness_score": 0.23,
    "label": "Provenance Guard found strong signs that this content was written by a human. Human-likelihood: 76%. No major AI-generation patterns were detected.",
    "status": "classified",
    "appeal_filed": false
  },
  {
    "entry_id": "74fa0fa1-14b3-4a72-9a8c-3a9ec8e60e24",
    "event_type": "classification",
    "content_id": "736578b7-b5ee-4583-9f41-91891fdf2b07",
    "creator_id": "demo-2",
    "timestamp": "2026-06-30T18:21:39.996682Z",
    "attribution": "likely_ai",
    "confidence": 0.874,
    "lexical_score": 0.76,
    "burstiness_score": 0.95,
    "label": "Provenance Guard found strong signs that this content may have been AI-generated. AI-likelihood: 87%. The creator can appeal this label if they believe it is wrong.",
    "status": "classified",
    "appeal_filed": false
  },
  {
    "entry_id": "cd198c85-b1fd-423d-b810-ac9f1856f738",
    "event_type": "appeal",
    "appeal_id": "7ce0f4ab-3171-4181-8a87-7f85567d51f6",
    "content_id": "21c2a8ea-af4a-41ea-8110-5fde92cb6681",
    "status": "under_review",
    "appeal_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical.",
    "original_attribution": "uncertain",
    "original_confidence": 0.55
  }
]
```

---

## Known Limitations

**Formal human academic writing will often score as uncertain or AI-leaning.** A human economics blog post reuses domain terms like "monetary policy" and "asset price inflation," which lowers type-token ratio. It also uses long, evenly structured sentences, which lowers burstiness variance. Both signals treat those patterns as AI-like even when the author is human. This is a direct consequence of measuring vocabulary repetition and sentence uniformity, not a generic "needs more training data" problem.

Short submissions (under ~50 words or fewer than 4 sentences) often return neutral signal scores because there is not enough text to measure patterns reliably.

---

## Spec Reflection

**How the spec helped:** Writing out the three label variants and confidence thresholds in `planning.md` before coding forced concrete decisions. Without that, it would have been tempting to flip a binary label at 0.5. The spec's asymmetric thresholds (0.85 for AI, 0.30 for human) shaped the whole UX: the system accuses rarely and defaults to uncertainty.

**Where implementation diverged:** The planning doc uses `content` and `submission_id` in the API contract. The milestone curl examples use `text` and `content_id`. I implemented both aliases so the API works with either naming style. I also added short-text calibration rules (blending scores when word count is between 25 and 50) because milestone test samples were shorter than the planning doc assumed, and raw heuristics returned too many neutral 0.50 scores on realistic inputs.

---

## AI Tool Usage

### Instance 1: Milestone 3 (Flask skeleton + lexical signal)

**What I asked:** Generate a Flask app with `POST /submit`, request validation, in-memory storage, and the lexical diversity signal function using my `planning.md` detection signals section and architecture diagram.

**What it produced:** A reasonable file structure (`app.py`, `detection/lexical.py`, `audit.py`, `storage.py`) with the right JSON output shape.

**What I revised:** I checked the signal scoring rules against my spec thresholds and fixed the word-count gate. I also aligned field names with the milestone (`text`, `content_id`) while keeping `content` as an alias.

### Instance 2: Milestone 4 (burstiness + confidence scoring)

**What I asked:** Generate the burstiness signal and weighted scoring logic from my detection signals and uncertainty representation sections.

**What it produced:** Working burstiness metrics and a weighted average function, but the milestone test samples did not separate well (formal AI text scored neutral because high vocabulary diversity looked human).

**What I revised:** I printed both signal scores separately, found lexical diversity was misreading polished AI text, and added short-text calibration plus a formal-text adjustment. I also verified the combined formula matched `(lexical * 0.40) + (burstiness * 0.60)` exactly before wiring it into the endpoint.

---

## How to Demo

### 1. Start the server

```bash
pip install -r requirements.txt
python app.py
```

Server runs at `http://localhost:5000`.

### 2. Submit human-like text (expect low score)

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably will not go back unless someone drags me there\", \"creator_id\": \"demo-human\"}" | python -m json.tool
```

Expected: `confidence` around **0.24**, `attribution` = `likely_human`, human-likelihood label.

### 3. Submit AI-like text (expect high score)

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"The results show that the results are clear and the results remain clear today. The data shows that the data is stable and the data remains stable today. The report says that the report is complete and the report remains complete today. The review finds that the review is consistent and the review remains consistent today.\", \"creator_id\": \"demo-ai\"}" | python -m json.tool
```

Expected: `confidence` around **0.87**, `attribution` = `likely_ai`, AI-likelihood label.

### 4. Submit borderline text (expect uncertain)

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.\", \"creator_id\": \"demo-borderline\"}" | python -m json.tool
```

Expected: `confidence` around **0.55**, `attribution` = `uncertain`.

### 5. Appeal a submission

Copy the `content_id` from step 4, then:

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d "{\"content_id\": \"PASTE-CONTENT-ID-HERE\", \"creator_reasoning\": \"I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical.\"}" | python -m json.tool
```

Expected: `status` = `under_review`, confirmation message.

### 6. View the audit log

```bash
curl -s http://localhost:5000/log | python -m json.tool
```

Expected: classification entries with both signal scores, plus an appeal entry with `appeal_reasoning` and `status: under_review`.

### 7. (Optional) Show rate limiting

Send 12 rapid requests. The 11th and 12th should return HTTP 429.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/submit` | Submit text for attribution analysis |
| POST | `/appeal` | Contest a classification |
| GET | `/log` | Retrieve the audit log |

See `planning.md` for full request/response contracts.

---

## Technology Stack

- Python 3.10+ with Flask
- Flask-Limiter for rate limiting
- Pure Python stylometric analysis (no ML model for core signals)
- In-memory storage for this prototype
