---
name: pex-ai-song-detector
description: >
  Detect whether an audio file contains AI-generated music using the Pex AI Song Detector API.
  Use this skill whenever the user wants to check if a song or audio file was created by AI,
  identify which AI music platform generated a track (Suno, Udio, Mureka, Sonauto, ElevenLabs, Boomy, etc.),
  or integrate AI music detection into a workflow. Trigger on phrases like "is this song AI generated",
  "detect AI music", "check if audio is AI", "AI song detection", "Pex detector", "AI music classifier",
  or any task involving classifying audio as human-made vs AI-generated. Also trigger when building
  pipelines or scripts that need to screen audio content for AI-generated music at scale.
---

# Pex AI Song Detector

Classify audio files as **AI-generated or human-made** music via the Pex AI Song Detector API. The API also identifies the AI generation platform (Suno, Udio, Mureka, Sonauto, ElevenLabs, Boomy, etc.) when possible.

Documentation: https://docs.pex.com/ai-song-detector/overview

## Quick facts

- **One prediction per file** — submit a single song, get one result.
- **Two input methods** — upload a file directly, or pass a public URL.
- **Auth** — OAuth 2.0 Client Credentials. Token is valid for **2 hours**; reuse it across requests.
- **Supported formats** — MP3, WAV, FLAC, AAC, M4A/MP4, OGG, WEBM, and other common audio formats.
- **Duration limits** — minimum 30 seconds, maximum 15 minutes.
- **File size limit** — 100 MB.
- **Privacy** — submitted audio is processed and immediately discarded; never stored or used for training.

## What the user needs to provide

1. **Client credentials** — a `CLIENT_ID` and `CLIENT_SECRET` issued by Pex. If the user hasn't provided them, ask before proceeding.
2. **Audio input** — either a local file path or a publicly accessible URL to the audio.

## API workflow

### Step 1 — Authenticate

```
POST https://api.ae.pex.com/oauth2/token
```

- **Auth:** HTTP Basic Auth with `CLIENT_ID` / `CLIENT_SECRET`.
- **Body:** `grant_type=client_credentials` (form-encoded).
- **Returns:** JSON with `access_token` (valid 2 hours).

### Step 2 — Submit audio

Choose the endpoint that matches the input type.

**Option A — File upload:**

```
POST https://api.ae.pex.com/v1/ai-detector/detect
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file=@<path_to_audio_file>
```

**Option B — URL:**

```
POST https://api.ae.pex.com/v1/ai-detector/detect-url
Authorization: Bearer <access_token>
Content-Type: application/x-www-form-urlencoded

url=<publicly_accessible_audio_url>
```

### Step 3 — Interpret the response

A successful response (`HTTP 200`, `status: "ok"`) returns:

| Field                  | Type    | Meaning |
|------------------------|---------|---------|
| `request_id`           | integer | Unique request identifier (useful for support). |
| `status`               | string  | `"ok"` when classification succeeded (see Status codes below for others). |
| `message`              | string  | Human-readable explanation. |
| `is_ai`                | boolean | `true` if the model classifies the song as AI-generated. Present only when status is `ok`. |
| `ai_score`             | float   | Score in [0, 1] — how strongly the model considers the audio AI-generated. Useful for sorting/QA, not a calibrated probability. Present only when status is `ok`. |
| `predicted_model`      | string  | AI platform name (e.g. `"suno"`, `"udio"`). May be `null` even when `is_ai` is `true` if attribution confidence is low. Present only when status is `ok`. |
| `predicted_model_score`| float   | Confidence score for the predicted platform. Present only when `predicted_model` is set. |

### Status codes (in `status` field)

| Status              | Meaning |
|---------------------|---------|
| `ok`                | Classification succeeded. |
| `invalid_file`      | Not a valid or parseable audio file. |
| `no_audio`          | Valid container but no audio track inside. |
| `too_short`         | Audio shorter than 30 seconds. |
| `too_long`          | Audio longer than 15 minutes. |
| `not_enough_music`  | Not enough musical content for reliable classification. |
| `not_found`         | URL could not be opened or file could not be retrieved. |
| `error`             | Other processing error. |

### HTTP error codes

| HTTP | Action |
|------|--------|
| 200  | Success — check the `status` field in the body. |
| 400  | Bad request (missing file/URL, wrong field name). Fix the request. |
| 401  | Invalid or expired token. Re-authenticate. |
| 413  | File exceeds 100 MB. Compress or trim. |
| 429  | Rate limited. Retry with exponential backoff. |
| 500, 502, 503 | Server-side issue. Retry with backoff (suggest 30 s). |

## Implementation guidance

- **Reuse the access token** across multiple requests; don't re-authenticate per file.
- **Input quality matters** — the detector is optimized for single songs. Avoid submitting DJ mixes, mashups, UGC compilations, or audio dominated by speech/silence.
- **`ai_score` is for ranking, not thresholding** — rely on the boolean `is_ai` for the classification decision. Score ranges can shift between model versions.
- See `scripts/detect.py` for simple API client CLI tool. It can process an arbitrary number of input files or urls.

## Batch processing — handling rate limits and auto-scaling correctly

**This is the most important section for any agent or pipeline processing multiple files.** The API backend auto-scales: it spins up more workers as traffic increases and scales down during inactivity. This means initial requests at high volume will likely hit rate limits (HTTP 429) until the service scales up to meet demand. A naive implementation will fail badly here. Read this section carefully.

### The naive mistake (do NOT do this)

A common broken pattern:

1. Send all N files at high concurrency.
2. Some succeed (HTTP 200), many get rate-limited (HTTP 429).
3. **Discard all results** and retry the entire batch at a lower rate.
4. The service sees lower traffic, scales down capacity.
5. Requests get rate-limited again at the new lower rate.
6. Repeat — the system never converges.

This fails because it re-sends already-successful requests (wasting quota and delaying new work) and the reduced traffic actually signals the backend to reduce capacity, creating a downward spiral.

### The correct pattern — persist successes, retry only failures

The right approach has three rules:

1. **Store every successful result immediately.** When a request returns HTTP 200, persist the result (to a file, database, or in-memory dict keyed by the input identifier). That file is done — never send it again.
2. **Retry only the requests that failed.** After each pass, build the retry queue from only the items that got a non-200 response (429, 500, 502, 503, etc.).
3. **Keep sending at a steady rate with backoff pauses.** When you hit a 429, pause briefly (start at ~30 s), then continue with the remaining failed items. Do NOT reduce your target throughput — the transient 429s are the signal that makes the backend scale up. As capacity grows, fewer requests fail, and eventually you reach full throughput.

### Pseudocode

```
results = {}          # key: file_id → value: API response
pending = all_files   # list of files still to process

while pending is not empty:
    failed = []

    for file in pending:
        response = send_request(file)

        if response.status_code == 200:
            results[file.id] = response.json()   # ✅ persist immediately
        elif response.status_code in (429, 500, 502, 503, 504):
            failed.append(file)                   # ⏳ will retry
            sleep(30)                             # back off briefly
        elif response.status_code == 401:
            refresh_token()                       # token expired, re-auth
            failed.append(file)                   # retry this file
        else:
            log_permanent_failure(file, response)  # 400, 413 etc. — won't retry

    pending = failed   # next pass: only the items that did not succeed

save(results)
```

### Why this works

The steady stream of requests (including the ones that get 429'd) tells the backend that demand is real and sustained. The service progressively spins up more workers. Each successive pass through the retry queue encounters fewer 429s because capacity has grown. Successful results accumulate monotonically — no work is ever repeated or lost. The system converges to the maximum processing rate naturally.

### Key parameters for agents building batch pipelines

| Parameter | Recommended value | Why |
|-----------|-------------------|-----|
| Initial concurrency | 5–10 parallel requests | Enough to trigger scaling without overwhelming. |
| Backoff on 429/5xx | 30 seconds (fixed or linear) | Gives backend time to add workers. Exponential backoff is fine but not required — the goal is sustained pressure, not retreat. |
| Max retries per file | 10+ | The service will scale; transient failures are expected early. Be patient. |
| Result persistence | After every successful response | Never lose a completed result. Write-ahead to disk or DB if the pipeline might crash. |
| Re-auth trigger | On HTTP 401, or proactively every ~90 min | Token lasts 2 hours. Don't let expiration surprise you mid-batch. |

## Bundled resources

- `scripts/detect.py` - Batch CLI processor: processes a directory of audio files with correct retry-only-failures logic, result persistence.
- `references/client-code-examples.md` - Curl and Python code examples.
