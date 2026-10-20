#!/usr/bin/env bash
# Run a Snyk open-source scan on every cloned repo in the list (repos/<name>/); keep the raw JSON per repo.
# Read-only for the repos (Snyk resolves the Maven/Gradle tree; it does not edit files).
#
# Usage (from the project root):
#   toolkit/scripts/snyk-scan.sh <out-dir> [--workflow <id> | --manifest <list-file>] [--reuse] [extra snyk args...]
#   e.g. toolkit/scripts/snyk-scan.sh workflows/wf-002-orders/snyk --workflow 2 --reuse --org=my-org
#
#   --reuse   keep a repo's earlier result in <out-dir> instead of scanning it again, when that result was made at
#             the clone's current commit (the commit is recorded in scan-index.tsv). Changed code is always rescanned.
#
# Needs the Snyk CLI, logged in. Which CLI is used, in this order:
#   1. $SNYK_CLI                - e.g. the CLI your Snyk VS Code extension downloaded:
#                                  export SNYK_CLI="/path/shown/in/the/extension/settings/snyk-macos-arm64"
#   2. `snyk` on your PATH      - brew tap snyk/tap && brew install snyk-cli   (or: npm install -g snyk)
#   3. common download folders of the Snyk VS Code extension / language server (see find_cli below)
# Log in once with the same SSO account as the extension:  bash toolkit/scripts/snyk-login.sh  (OAuth2, opens your browser).
#
# Never scans inside the folders in toolkit/ignore-dirs.txt (target/, node_modules/, ...): they are passed to
# Snyk as --exclude=..., merged with any --exclude=... you give.
#
# Outputs in <out-dir>:
#   <repo-name>.json   raw `snyk test --all-projects --json`
#   scan-index.tsv     repo <TAB> path <TAB> exit-code <TAB> meaning <TAB> commit scanned
# Then:  python3 -I toolkit/scripts/parse-snyk.py <out-dir>/*.json --md ... --csv ...
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
out=${1:?out dir required}
shift
manifest_args=()
if [[ "${1:-}" == "--manifest" || "${1:-}" == "--workflow" ]]; then manifest_args=("$1" "$2"); shift 2; fi

# shellcheck source=snyk-common.sh
. "$(dirname "$0")/snyk-common.sh"

if ! snyk_bin=$(find_cli); then
  cli_missing_help
  exit 127
fi
echo "Using Snyk CLI: $snyk_bin" >&2
# Works for every kind of login: browser/SSO (OAuth), service-account client credentials, API token.
if ! snyk_logged_in; then
  echo "Snyk is not logged in - run: bash toolkit/scripts/snyk-login.sh   (opens your browser for SSO)" >&2
  exit 126
fi

mkdir -p "$out"
out=$(cd "$out" && pwd)
previous="$out/.scan-index.previous"
if [[ -f "$out/scan-index.tsv" ]]; then cp "$out/scan-index.tsv" "$previous"; else : > "$previous"; fi
printf 'repo\tpath\texit\tmeaning\tcommit\n' > "$out/scan-index.tsv"

# Build output and dependency folders are never scanned: merge them into one --exclude=...
exclude=$(python3 -I "$here/script-helpers.py" ignore-dirs --comma)
snyk_args=()
reuse=false
for arg in "$@"; do
  case "$arg" in
    --reuse) reuse=true ;;
    --exclude=*) exclude="${arg#--exclude=},$exclude" ;;
    *) snyk_args+=("$arg") ;;
  esac
done
snyk_args+=("--exclude=$exclude")

# ${arr[@]+...} form: bash 3.2 (macOS) treats an empty array as unbound under `set -u`.
repos=$(python3 -I "$here/repos.py" ${manifest_args[@]+"${manifest_args[@]}"} list) || exit 2
while IFS=$'\t' read -r name dir _rest; do
  [[ -z "$name" ]] && continue
  if [[ ! -d "$dir" ]]; then
    printf '%s\t%s\t-\tnot cloned - run repos.py clone %s\n' "$name" "$dir" "$name" >> "$out/scan-index.tsv"
    echo "SKIP $name: $dir does not exist (not cloned yet?)" >&2
    continue
  fi
  commit=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo -)
  if $reuse && [[ -s "$out/$name.json" ]]; then
    # An earlier clean result (exit 0/1) for the same repo at the same commit is still valid.
    earlier=$(awk -F'\t' -v n="$name" -v c="$commit" \
      '$1==n && $5==c && ($3=="0" || $3=="1") { sub(/ \(reused\)$/, "", $4); print $3 "\t" $4; exit }' "$previous")
    if [[ -n "$earlier" ]]; then
      printf '%s\t%s\t%s (reused)\t%s\n' "$name" "$dir" "$earlier" "$commit" >> "$out/scan-index.tsv"
      echo "REUSE $name: already scanned at $commit" >&2
      continue
    fi
  fi
  echo "SCAN $name ($dir)" >&2
  # --all-projects picks up every pom/gradle file under the path (multi-module included).
  (cd "$dir" && "$snyk_bin" test --all-projects --json "${snyk_args[@]}") > "$out/$name.json" 2> "$out/$name.err"
  code=$?
  case $code in
    0) meaning="no vulnerabilities" ;;
    1) meaning="vulnerabilities found" ;;
    2) meaning="scan failed - see $name.err" ;;
    3) meaning="no supported project found" ;;
    *) meaning="unexpected exit" ;;
  esac
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$dir" "$code" "$meaning" "$commit" >> "$out/scan-index.tsv"
done <<< "$repos"

rm -f "$previous"
column -t -s $'\t' "$out/scan-index.tsv" >&2
