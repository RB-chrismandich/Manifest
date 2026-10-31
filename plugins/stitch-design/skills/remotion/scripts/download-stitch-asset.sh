#!/bin/bash

# Download Stitch screen asset with proper handling of Google Cloud Storage URLs
# Usage: ./download-stitch-asset.sh "https://storage.googleapis.com/..." "output-path.png"

# Signed URLs are capabilities; stop inherited tracing before reading arguments.
set +x
set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <download_url> <output_path>"
    echo "Example: $0 'https://storage.googleapis.com/stitch/screenshot.png' 'assets/screen.png'"
    exit 1
fi

DOWNLOAD_URL="$1"
OUTPUT_PATH="$2"

# Create directory if it doesn't exist
OUTPUT_DIR=$(dirname "$OUTPUT_PATH")
mkdir -p "$OUTPUT_DIR"

echo "Downloading Stitch asset..."
echo "Saving to: $OUTPUT_PATH"

# Use curl with follow redirects; -f fails on HTTP errors so an error
# response (e.g. an expired signed URL) is not saved as the asset
# Ignore curlrc tracing/write-out settings and suppress raw diagnostics, which
# can repeat signed URLs. Keep the numeric exit code as the failure diagnostic.
if curl -q -s -L -f -o "$OUTPUT_PATH" --url "$DOWNLOAD_URL" > /dev/null 2>&1; then
    echo "✓ Successfully downloaded to $OUTPUT_PATH"

    # Display file size for verification
    if command -v stat &> /dev/null; then
        FILE_SIZE=$(stat -f%z "$OUTPUT_PATH" 2> /dev/null || stat -c%s "$OUTPUT_PATH" 2> /dev/null)
        echo "  File size: $FILE_SIZE bytes"
    fi
else
    CURL_STATUS=$?
    echo "✗ Download failed (curl exit $CURL_STATUS)"
    rm -f "$OUTPUT_PATH"
    exit 1
fi
