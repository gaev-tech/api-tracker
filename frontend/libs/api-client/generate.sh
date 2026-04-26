#!/bin/bash
# Generate Angular API client from OpenAPI spec
# Usage: ./generate.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SPEC_FILE="$SCRIPT_DIR/../../../contracts/openapi/openapi.yaml"
OUTPUT_DIR="$SCRIPT_DIR/src/generated"

rm -rf "$OUTPUT_DIR"

npx --registry https://registry.npmjs.org/ @openapitools/openapi-generator-cli generate \
  -i "$SPEC_FILE" \
  -g typescript-angular \
  -o "$OUTPUT_DIR" \
  --additional-properties=ngVersion=21.0.0,providedInRoot=true,stringEnums=true

echo "API client generated at $OUTPUT_DIR"
