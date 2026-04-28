# Pex AI Song Detector — Code Examples

Full reference: https://docs.pex.com/ai-song-detector

See [SKILL.md](../SKILL.md) for API reference, constraints, status codes, and batch processing guidance.

---

## Curl examples

### Authenticate

```bash
CLIENT_ID="YOUR_CLIENT_ID"
CLIENT_SECRET="YOUR_CLIENT_SECRET"

TOKEN_RESPONSE=$(curl -s \
  -u "${CLIENT_ID}:${CLIENT_SECRET}" \
  -d "grant_type=client_credentials" \
  "https://api.ae.pex.com/oauth2/token")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')
```

### Detect — file upload

```bash
curl -s \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -F "file=@song.mp3" \
  "https://api.ae.pex.com/v1/ai-detector/detect"
```

### Detect — URL

> The URL must allow direct download without authentication. If it can't be opened, the response `status` will be `not_found`.

```bash
curl -s \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "url=https://example.com/song.mp3" \
  "https://api.ae.pex.com/v1/ai-detector/detect-url"
```

---

## Python examples

### Minimal

```python
import requests

# Authenticate
token_resp = requests.post(
    "https://api.ae.pex.com/oauth2/token",
    data={"grant_type": "client_credentials"},
    auth=("YOUR_CLIENT_ID", "YOUR_CLIENT_SECRET"),
)
token_resp.raise_for_status()
access_token = token_resp.json()["access_token"]

# Detect (file upload)
with open("song.mp3", "rb") as f:
    resp = requests.post(
        "https://api.ae.pex.com/v1/ai-detector/detect",
        headers={"Authorization": f"Bearer {access_token}"},
        files={"file": f},
    )
result = resp.json()
print(result["is_ai"], result["ai_score"])
```

### Detect via URL

```python
resp = requests.post(
    "https://api.ae.pex.com/v1/ai-detector/detect-url",
    headers={"Authorization": f"Bearer {access_token}"},
    data={"url": "https://example.com/song.mp3"},
)
result = resp.json()
```