#!/usr/bin/env bash
# Run a Snyk open-source scan on every cloned repo in the list (repos/<name>/); keep the raw JSON per repo.
# Read-only for the repos (Snyk resolves the Maven/Gradle tree; it does not edit files).
#
# Usage (from the project root):
#   toolkit/scripts/snyk-scan.sh <out-dir> [--workflow <id> | --manifest <list-file>] [extra snyk args...]
#   e.g. toolkit/scripts/snyk-scan.sh workflows/2026-10-15-x/snyk --org=my-org
#
# Needs the Snyk CLI, logged in. Which CLI is used, in this order:
#   1. $SNYK_CLI                - e.g. the CLI your Snyk VS Code extension downloaded:
#                                  export SNYK_CLI="/path/shown/in/the/extension/settings/snyk-macos-arm64"
#   2. `snyk` on your PATH      - brew tap snyk/tap && brew install snyk-cli   (or: npm install -g snyk)
#   3. common download folders of the Snyk VS Code extension / language server (see find_cli below)
# Log in once with the same SSO account as the extension:  "$SNYK_CLI" auth  (or: snyk auth), or SNYK_TOKEN.
#
# Outputs in <out-dir>:
#   <repo-name>.json   raw `snyk test --all-projects --json`
#   scan-index.tsv     repo <TAB> path <TAB> exit-code <TAB> meaning
# Then:  python3 -I toolkit/scripts/parse-snyk.py <out-dir>/*.json --md ... --csv ...
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
out=${1:?out dir required}
shift
manifest_args=()
if [[ "${1:-}" == "--manifest" || "${1:-}" == "--workflow" ]]; then manifest_args=("$1" "$2"); shift 2; fi

find_cli() {
  if [[ -n "${SNYK_CLI:-}" ]]; then
    [[ -x "$SNYK_CLI" && ! -d "$SNYK_CLI" ]] && { echo "$SNYK_CLI"; return 0; }
    echo "SNYK_CLI is set to '$SNYK_CLI', but that is not an executable file." >&2
    return 1
  fi
  command -v snyk 2>/dev/null && return 0
  # Where the Snyk VS Code extension / language server usually downloads its CLI. Locations vary by
  # version and OS - if yours is elsewhere, set SNYK_CLI (the path is in the extension's settings).
  local c
  for c in "$HOME/Library/Application Support/snyk/"snyk-macos* \
           "$HOME/Library/Application Support/Code/User/globalStorage/snyk-security.snyk-vulnerability-scanner/"snyk* \
           "$HOME/.local/share/snyk/"snyk-linux* \
           "$HOME/.config/Code/User/globalStorage/snyk-security.snyk-vulnerability-scanner/"snyk*; do
    [[ -f "$c" && -x "$c" ]] && { echo "$c"; return 0; }
  done
  return 1
}

if ! snyk_bin=$(find_cli); then
  cat >&2 <<'MSG'
Snyk CLI not found. Any one of these works:
  - Use the CLI your Snyk VS Code extension already downloaded (its path is in the extension's settings):
      export SNYK_CLI="/path/to/snyk-macos-arm64"
  - Install it:   brew tap snyk/tap && brew install snyk-cli     (or: npm install -g snyk)
Then log in once with the same SSO account:  "$SNYK_CLI" auth   (or: snyk auth)
Or export `snyk test --all-projects --json` from CI and pass the file to parse-snyk.py instead.
MSG
  exit 127
fi
echo "Using Snyk CLI: $snyk_bin" >&2
# `whoami` works for both kinds of login: a token (snyk config / SNYK_TOKEN) and browser/SSO (OAuth).
if [[ -z "${SNYK_TOKEN:-}" ]] && ! "$snyk_bin" whoami --experimental >/dev/null 2>&1; then
  echo "Snyk is not logged in - run: \"$snyk_bin\" auth   (opens your browser for SSO), or export SNYK_TOKEN." >&2
  exit 126
fi

mkdir -p "$out"
out=$(cd "$out" && pwd)
printf 'repo\tpath\texit\tmeaning\n' > "$out/scan-index.tsv"

# ${arr[@]+...} form: bash 3.2 (macOS) treats an empty array as unbound under `set -u`.
repos=$(python3 -I "$here/repos.py" ${manifest_args[@]+"${manifest_args[@]}"} list) || exit 2
while IFS=$'\t' read -r name dir _rest; do
  [[ -z "$name" ]] && continue
  if [[ ! -d "$dir" ]]; then
    printf '%s\t%s\t-\tnot cloned - run repos.py clone %s\n' "$name" "$dir" "$name" >> "$out/scan-index.tsv"
    echo "SKIP $name: $dir does not exist (not cloned yet?)" >&2
    continue
  fi
  echo "SCAN $name ($dir)" >&2
  # --all-projects picks up every pom/gradle file under the path (multi-module included).
  (cd "$dir" && "$snyk_bin" test --all-projects --json "$@") > "$out/$name.json" 2> "$out/$name.err"
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
