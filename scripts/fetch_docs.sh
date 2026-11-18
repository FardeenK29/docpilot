#!/usr/bin/env bash
# Fetch the FastAPI docs (MIT licensed) into data/fastapi-src. Only docs/en/docs is checked out.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d data/fastapi-src ]; then
  git clone -q --depth 1 --filter=blob:none --sparse https://github.com/fastapi/fastapi.git data/fastapi-src
fi
git -C data/fastapi-src sparse-checkout set docs/en/docs
echo "docs ready: $(find data/fastapi-src/docs/en/docs -name '*.md' | wc -l | tr -d ' ') markdown files"
