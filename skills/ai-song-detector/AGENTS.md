# Pex AI Song Detector

Classifies audio files as AI-generated or human-made via the Pex AI Song Detector API. This skill supports single file uploads and batch processing of local files or remote URLs. See `SKILL.md` for full API reference, file constraints, and status codes.

## Credentials

Set these environment variables before using the API:

```
PEX_CLIENT_ID=<your_client_id>
PEX_CLIENT_SECRET=<your_client_secret>
```

## Response shape

```json
{
  "request_id": 806957142976735233,
  "status": "ok",
  "message": "ok",
  "is_ai": true,
  "ai_score": 0.9992,
  "predicted_model": "suno",
  "predicted_model_score": 0.9723
}
```

Key fields (present only when `status` is `"ok"`):
- `is_ai` (bool) — the classification decision. Use this for logic, not `ai_score`.
- `ai_score` (float, 0–1) — ranking/QA signal. Not a calibrated probability.
- `predicted_model` (string|null) — AI platform: `"suno"`, `"udio"`, `"mureka"`, `"sonauto"`, `"elevenlabs"`, `"boomy"`, `"lyria"`, `"producer.ai"`. Null when attribution confidence is low.
- `predicted_model_score` (float) — attribution confidence. Present when `predicted_model` is set.

## Usage

### Batch processing

Process multiple local files or URLs and save results to a CSV. The script handles authentication, retries on transient failures, and follows the API's scaling behavior.

```bash
# Process local files
python scripts/detect.py --client-id $PEX_CLIENT_ID --client-secret $PEX_CLIENT_SECRET song1.mp3 song2.mp3

# Process URLs
python scripts/detect.py --client-id $PEX_CLIENT_ID --client-secret $PEX_CLIENT_SECRET --url https://example.com/song.mp3
```

Results are saved to `results.csv` by default. Use `--help` for all options.

### Programmatic access

Use the API directly for single file detection:

```python
import requests

# 1. Authenticate
token_resp = requests.post(
    'https://api.ae.pex.com/oauth2/token',
    data={'grant_type': 'client_credentials'},
    auth=(PEX_CLIENT_ID, PEX_CLIENT_SECRET),
)
access_token = token_resp.json()['access_token']

# 2. Detect
with open('song.mp3', 'rb') as f:
    resp = requests.post(
        'https://api.ae.pex.com/v1/ai-detector/detect',
        headers={'Authorization': f'Bearer {access_token}'},
        files={'file': f},
    )
result = resp.json()
print(result['is_ai'], result['ai_score'], result.get('predicted_model'))
```
