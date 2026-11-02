#!/bin/bash
# Daily: rebuild the Mirrors Studio shop from Print Kit's records of what is
# live on Redbubble and Zazzle, and publish only if something changed. Run
# from the main site's daily sync (kirwana.github.io/tools/sync.sh), so it
# shares its launchd job and log.
cd "$(dirname "$0")/.." || exit 1
echo "-- art $(date '+%Y-%m-%d %H:%M')"
/usr/bin/git pull -q --rebase || echo "pull failed; building on what is here"
/usr/bin/python3 tools/build.py || { echo "art build failed"; exit 1; }
if [ -z "$(/usr/bin/git status --porcelain)" ]; then
  echo "art: no change"
  exit 0
fi
/usr/bin/git add -A
/usr/bin/git commit -q -m "Shop: synced with Redbubble and Zazzle $(date '+%Y-%m-%d')"
/usr/bin/git push -q && echo "art: published" || echo "art: push failed"
