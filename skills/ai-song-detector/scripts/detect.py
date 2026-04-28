#!/usr/bin/env python3
"""
Pex AI Song Detector - batch processor.

Submits a list of audio files or URLs to the Pex AI Song Detector API and writes the results to a CSV.
Each input is retried independently up to 5 times on transient failures (HTTP 429, 5xx, network errors).

Usage:
    # Process local media files
    python detect.py --client-id YOUR_ID --client-secret YOUR_SECRET song1.mp3 song2.mp3 --output results.csv

    # Process URLs
    python detect.py --client-id YOUR_ID --client-secret YOUR_SECRET \
        -u https://example.com/a.mp3 https://example.com/b.mp3 --output results.csv

Example of output csv:
    id,request_id,status,message,is_ai,ai_score,predicted_model,predicted_model_score
    real_song.mp3,859978972511678465,ok,ok,0,0.0188,,
    ai_song.mp3,859979019756449281,ok,ok,1,0.9964,suno,1.0

Requirements:
    requests

Parallel processing:
    This demo script doesn't show how to process multiple files in parallel, only in a sequence.

    If you implement parallel processing, you should consider the following: The API auto-scales: it adds workers
    as traffic increases and removes them during inactivity. When processing many inputs, initial requests may hit
    rate limits (HTTP 429) until the service scales up.
"""

import argparse
import csv
import logging
import sys
import time

import requests

logger = logging.getLogger(__name__)

TOKEN_ENDPOINT = 'https://api.ae.pex.com/oauth2/token'
DETECT_FILE_ENDPOINT = 'https://api.ae.pex.com/v1/ai-detector/detect'
DETECT_URL_ENDPOINT = 'https://api.ae.pex.com/v1/ai-detector/detect-url'


def get_access_token(client_id: str, client_secret: str) -> str:
    """Exchange client credentials for an OAuth access token.

    :param client_id: OAuth client ID.
    :param client_secret: OAuth client secret.
    :returns: Bearer access token (valid for ~2 hours).
    :raises requests.HTTPError: if the token endpoint rejects the credentials.
    """
    logger.info("Authenticating.")
    resp = requests.post(
        TOKEN_ENDPOINT,
        data={'grant_type': 'client_credentials'},
        auth=(client_id, client_secret),
    )
    resp.raise_for_status()

    logger.info("Authenticated.")

    return resp.json()['access_token']


def write_results(output_path: str, results: list[dict]):
    """Write results as CSV using the documented response schema.

    Columns match the fields documented at https://docs.pex.com/ai-song-detector/api-documentation, plus a leading
    `id` column holding the input URL or filename.

    :param output_path: Destination CSV path. Overwritten if it exists.
    :param results: List of result dicts produced by ``process_batch()``.
    """
    fields = ['id', 'request_id', 'status', 'message', 'is_ai', 'ai_score', 'predicted_model', 'predicted_model_score']
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in results:
            row = {k: int(v) if isinstance(v, bool) else v for k, v in r.items()}  # write bool as 0/1
            writer.writerow(row)


def process_batch(
        inputs: list[str],
        is_url: bool,
        client_id: str,
        client_secret: str,
        max_retries: int = 5,
) -> list[dict]:
    """Detect AI content for each input, with per-input retries.

    Iterates through ``inputs`` one at a time. For each input, transient
    failures (network errors, HTTP 429/5xx, expired tokens) are retried up to
    ``max_retries`` times.

    The batch stops early - returning the results collected so far - if any of
    the following occurs on a single input:

    * The retry budget is exhausted.
    * The API returns a permanent failure (HTTP 400 or 413).
    * A local file cannot be opened.

    :param inputs: List of audio file paths (when ``is_url`` is False) or URLs
        (when ``is_url`` is True).
    :param is_url: If True, ``inputs`` are treated as URLs submitted to the
        detect-url endpoint. If False, they are treated as local file paths
        uploaded to the detect endpoint.
    :param client_id: OAuth client ID.
    :param client_secret: OAuth client secret.
    :param max_retries: Maximum number of attempts per input before giving up
        on that input (and aborting the batch). Defaults to 5.
    :returns: List of result dicts, one per successfully processed input. Each
        dict contains an ``id`` field (the URL or filename) merged with the
        API response body.
    """
    results = []

    access_token = get_access_token(client_id, client_secret)

    # Loop through each input
    for i, item in enumerate(inputs, start=1):
        item_done = False

        # Try to process the input, retrying on transient errors up to max_retries
        for attempt in range(1, max_retries + 1):
            logger.info("Processing item %d of %d, attempt %d.", i, len(inputs), attempt)

            # Submit the request to the API
            try:
                headers = {'Authorization': f'Bearer {access_token}'}
                if is_url:
                    # Use URL endpoint for URLs
                    resp = requests.post(DETECT_URL_ENDPOINT, headers=headers, data={'url': item})
                else:
                    # Use file endpoint for locally stored media files
                    with open(item, 'rb') as f:
                        resp = requests.post(DETECT_FILE_ENDPOINT, headers=headers, files={'file': f})
            except OSError as e:
                logger.error("Cannot read file %s: %s. Aborting.", item, e)
                return results
            except requests.RequestException as e:
                logger.warning("Network error: %s for %s - retrying (attempt %d/%d).", e, item, attempt, max_retries)
                time.sleep(attempt)
                continue

            # Check API response
            if resp.status_code == 200:
                # Success - store result and continue to the next input
                result = resp.json()
                results.append({'id': item, **result})
                item_done = True
                break

            # Non-retryable errors, return results collected so far and abort.
            if resp.status_code in {400, 413}:
                logger.error("HTTP %d for %s - permanent failure. Aborting.", resp.status_code, item)
                return results

            # Expired token, re-authenticate and retry
            if resp.status_code == 401:
                logger.warning("Token rejected, re-authenticating.")
                access_token = get_access_token(client_id, client_secret)

            # Retry: 401 after re-auth, 429, 5xx, or any unknown status
            logger.warning("HTTP %d for %s - retrying (attempt %d/%d).", resp.status_code, item, attempt, max_retries)
            time.sleep(attempt)

        if not item_done:
            logger.error("Giving up on %s after %d attempts. Aborting.", item, max_retries)
            return results

    logger.info("Completed: %d/%d.", len(results), len(inputs))

    return results


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    parser = argparse.ArgumentParser(
        description="Pex AI Song Detector - batch processor. Retries transient failures "
                    "(HTTP 429, 5xx, network errors) per input. If an input exhausts its retries or returns a permanent "
                    "failure, the batch aborts and results gathered so far are written to the output file."
    )
    parser.add_argument('--client-id', required=True, help="OAuth client ID")
    parser.add_argument('--client-secret', required=True, help="OAuth client secret")
    parser.add_argument('-r', '--max-retries', type=int, default=5, help="Max retries per input")
    parser.add_argument('-u', '--url', action='store_true', help="Treat inputs as URLs instead of local file paths.")
    parser.add_argument('-o', '--output', default='results.csv', help="Output CSV file (default: results.csv).")
    parser.add_argument('inputs', nargs='+', help="Audio files to process (default), or URLs if -u/--url is set.")

    args = parser.parse_args()

    results = process_batch(args.inputs, args.url, args.client_id, args.client_secret, args.max_retries)
    write_results(args.output, results)
    logger.info("Results saved to: %s", args.output)

    if len(results) < len(args.inputs):
        # Something went wrong - not all inputs were processed.
        logger.error("Batch aborted: %d/%d inputs processed.", len(results), len(args.inputs))
        sys.exit(1)


if __name__ == '__main__':
    main()
