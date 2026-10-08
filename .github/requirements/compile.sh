#!/bin/sh
# Regenerates the hash-locked files next to this script. Run after changing a .in file or to update:
#   sh .github/requirements/compile.sh
set -e
cd "$(dirname "$0")"
for name in test lint run hf bot; do
  uv pip compile --universal --generate-hashes --python-version 3.9 --quiet "$name.in" -o "$name.txt"
done
