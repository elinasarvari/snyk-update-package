#!/usr/bin/env bash
# Shared by snyk-scan.sh and snyk-login.sh (source it). PowerShell twin: snyk-common.ps1.
#   find_cli          -> path of the Snyk CLI to use ($SNYK_CLI, `snyk` on PATH, the VS Code extension's download)
#   cli_missing_help  -> how to get one (stderr)
#   snyk_logged_in    -> true only if Snyk itself accepts the login: `snyk whoami` sends the stored OAuth token (or
#                        SNYK_TOKEN / SNYK_OAUTH_TOKEN from the environment) to Snyk and succeeds. Never assumed.
#   snyk_user         -> the logged-in username, if any

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

cli_missing_help() {
  cat >&2 <<'MSG'
Snyk CLI not found. Any one of these works:
  - Use the CLI your Snyk VS Code extension already downloaded (its path is in the extension's settings):
      export SNYK_CLI="/path/to/snyk-macos-arm64"
  - Install it:   brew tap snyk/tap && brew install snyk-cli     (or: npm install -g snyk)
Then log in once with the same SSO account:  bash toolkit/scripts/snyk-login.sh   (opens your browser)
Or export `snyk test --all-projects --json` from CI and pass the file to parse-snyk.py instead.
MSG
}

snyk_logged_in() {
  # Always ask Snyk - also when a token is set in the environment (it could be expired or for another region).
  "$snyk_bin" whoami --experimental >/dev/null 2>&1
}

snyk_user() {
  "$snyk_bin" whoami --experimental 2>/dev/null | tail -1
}
