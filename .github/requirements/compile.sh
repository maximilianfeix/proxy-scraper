#!/bin/sh
# Regenerates the hash-locked files next to this script. Run after changing a .in file or to update:
#   sh .github/requirements/compile.sh
set -e
cd "$(dirname "$0")"
# the bot's runtime lock lives next to the bot: the deploy ships bot/ and installs it with --require-hashes.
# It comes first – bot.in (the bot's test lock) is constrained to it
uv pip compile --universal --generate-hashes --python-version 3.9 --quiet ../../bot/requirements.txt \
  -o ../../bot/requirements.lock
for name in test lint run hf bot; do
  uv pip compile --universal --generate-hashes --python-version 3.9 --quiet "$name.in" -o "$name.txt"
done
