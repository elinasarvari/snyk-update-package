#!/usr/bin/env bash
# Log the Snyk CLI in with OAuth2 - no clicking around in the VS Code extension.
# PowerShell twin: snyk-login.ps1 (same options, same exit codes).
#
# Usage: snyk-login.sh [--status | --logout | --force] [--browser | --client-credentials] [--endpoint <url>]
#   (no option)            already logged in? say who. Otherwise log in:
#                            - SNYK_CLIENT_ID + SNYK_CLIENT_SECRET set -> OAuth2 client credentials (service account,
#                              no browser; Snyk Enterprise)
#                            - otherwise -> OAuth2 in your browser: it opens by itself, sign in with your company SSO.
#                              The CLI keeps a token that renews itself, so this is a one-time step.
#   --status               only report: exit 0 if logged in, 126 if not
#   --force                log in again even if already logged in
#   --browser              always use the browser login, even if client credentials are set
#   --client-credentials   always use client credentials (fails if SNYK_CLIENT_ID / SNYK_CLIENT_SECRET aren't set)
#   --endpoint <url>       first point the CLI at your Snyk region / private instance (saved in the CLI config),
#                          e.g. --endpoint https://api.eu.snyk.io   (check the URL with your Snyk admin)
#   --logout               log the CLI out
#
# The client secret is read from the environment only, and never printed or written to a file.
# Exit codes: 0 logged in (or logged out with --logout), 126 not logged in, 127 no Snyk CLI, 64 bad arguments
set -uo pipefail
# shellcheck source=snyk-common.sh
. "$(dirname "$0")/snyk-common.sh"

mode=login force=false method=auto endpoint=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --status) mode=status ;;
    --logout) mode=logout ;;
    --force) force=true ;;
    --browser) method=browser ;;
    --client-credentials) method=client ;;
    --endpoint) [[ $# -ge 2 ]] || { echo "--endpoint needs a URL" >&2; exit 64; }; endpoint=$2; shift ;;
    *) echo "unknown option $1 (see the top of $0)" >&2; exit 64 ;;
  esac
  shift
done

if ! snyk_bin=$(find_cli); then
  cli_missing_help
  exit 127
fi
echo "Using Snyk CLI: $snyk_bin"

if [[ -n "$endpoint" ]]; then
  "$snyk_bin" config set "endpoint=$endpoint" >/dev/null || { echo "could not set the endpoint" >&2; exit 64; }
  echo "Snyk endpoint set to $endpoint"
fi

case "$mode" in
  status)
    if snyk_logged_in; then echo "Logged in to Snyk as $(snyk_user)"; exit 0; fi
    echo "Not logged in to Snyk - run: bash toolkit/scripts/snyk-login.sh"
    exit 126 ;;
  logout)
    "$snyk_bin" logout >/dev/null 2>&1
    echo "Logged out of Snyk"
    exit 0 ;;
esac

if ! $force && snyk_logged_in; then
  echo "Already logged in to Snyk as $(snyk_user) - nothing to do"
  exit 0
fi
if [[ -n "${SNYK_TOKEN:-}${SNYK_OAUTH_TOKEN:-}" ]]; then
  echo "Note: SNYK_TOKEN / SNYK_OAUTH_TOKEN is set in this shell, Snyk rejects it, and the CLI uses it instead of a login. Unset it, or replace it."
fi

if [[ "$method" == auto ]]; then
  if [[ -n "${SNYK_CLIENT_ID:-}" && -n "${SNYK_CLIENT_SECRET:-}" ]]; then method=client; else method=browser; fi
fi

if [[ "$method" == client ]]; then
  if [[ -z "${SNYK_CLIENT_ID:-}" || -z "${SNYK_CLIENT_SECRET:-}" ]]; then
    echo "--client-credentials needs SNYK_CLIENT_ID and SNYK_CLIENT_SECRET (a Snyk service account)" >&2
    exit 64
  fi
  echo "Logging in with OAuth2 client credentials (service account ${SNYK_CLIENT_ID}) ..."
  "$snyk_bin" auth --auth-type=oauth "--client-id=$SNYK_CLIENT_ID" "--client-secret=$SNYK_CLIENT_SECRET" >/dev/null 2>&1
else
  echo "Opening your browser for the Snyk login (OAuth2). Sign in with your company SSO, then come back here."
  echo "If no browser opens, copy the link the Snyk CLI prints below into your browser."
  "$snyk_bin" auth --auth-type=oauth
fi

if snyk_logged_in; then
  echo "Logged in to Snyk as $(snyk_user)"
  exit 0
fi
echo "Snyk login did not complete. Try again, or check with your Snyk admin that SSO login is enabled for you." >&2
exit 126
