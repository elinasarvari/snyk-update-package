#!/usr/bin/env bash
# Run a Snyk open-source scan on every cloned repo in the manifest; keep the raw JSON per repo.
# Read-only for the repos (Snyk resolves the Maven/Gradle tree; it does not edit files).
#
# Usage (from the project root):
#   workflow/scripts/snyk-scan.sh <out-dir> [--manifest <repos.txt>] [extra snyk args...]
#   e.g. workflow/scripts/snyk-scan.sh upgrades/2026-10-15-x/snyk --org=my-org
#
# Needs the Snyk CLI, authenticated:
#   brew tap snyk/tap && brew install snyk-cli     (or: npm install -g snyk)
#   snyk auth                                       (or export SNYK_TOKEN=...)
#
# Outputs in <out-dir>:
#   <repo-name>.json   raw `snyk test --all-projects --json`
#   scan-index.tsv     repo <TAB> path <TAB> exit-code <TAB> meaning
# Then:  python3 -I workflow/scripts/parse-snyk.py <out-dir>/*.json --md ... --csv ...
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
out=${1:?out dir required}
shift
manifest_args=()
if [[ "${1:-}" == "--manifest" ]]; then manifest_args=(--manifest "$2"); shift 2; fi

if ! command -v snyk >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Snyk CLI not found. Install and authenticate, then re-run:
  brew tap snyk/tap && brew install snyk-cli   # or: npm install -g snyk
  snyk auth                                    # or: export SNYK_TOKEN=<token from app.snyk.io/account>
Alternatively export `snyk test --all-projects --json` from CI and pass the file to parse-snyk.py.
EOF
  exit 127
fi
if [[ -z "${SNYK_TOKEN:-}" ]] && ! snyk config get api >/dev/null 2>&1; then
  echo "Snyk is not authenticated - run 'snyk auth' or export SNYK_TOKEN." >&2
  exit 126
fi

mkdir -p "$out"
out=$(cd "$out" && pwd)
printf 'repo\tpath\texit\tmeaning\n' > "$out/scan-index.tsv"

repos=$(python3 -I "$here/repos.py" "${manifest_args[@]}" list) || exit 2
while IFS=$'\t' read -r name dir _rest; do
  [[ -z "$name" ]] && continue
  if [[ ! -d "$dir" ]]; then
    printf '%s\t%s\t-\tnot cloned - run repos.py clone %s\n' "$name" "$dir" "$name" >> "$out/scan-index.tsv"
    echo "SKIP $name: $dir does not exist (not cloned?)" >&2
    continue
  fi
  echo "SCAN $name ($dir)" >&2
  # --all-projects picks up every pom/gradle file under the path (multi-module included).
  (cd "$dir" && snyk test --all-projects --json "$@") > "$out/$name.json" 2> "$out/$name.err"
  code=$?
  case $code in
    0) meaning="no vulnerabilities" ;;
    1) meaning="vulnerabilities found" ;;
    2) meaning="scan failed - see $name.err" ;;
    3) meaning="no supported project found" ;;
    *) meaning="unexpected exit" ;;
  esac
  printf '%s\t%s\t%s\t%s\n' "$name" "$dir" "$code" "$meaning" >> "$out/scan-index.tsv"
done <<< "$repos"

column -t -s $'\t' "$out/scan-index.tsv" >&2
