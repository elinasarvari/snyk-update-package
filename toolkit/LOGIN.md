# /dep-login: log the Snyk CLI in with OAuth2

Logs the Snyk CLI in, the same SSO login the VS Code extension does when you click "Authenticate", started from
here. Run it on its own (`/dep-login`), or let `/dep-scan` / `/dep-run` start it when the CLI isn't logged in.
The script is `toolkit/scripts/snyk-login.sh` (Windows: `snyk-login.ps1`). Options are listed at the top of it.

## Steps

1. **Check:** `bash toolkit/scripts/snyk-login.sh --status`.
   - Exit 0 → already logged in: report the username and stop.
   - Exit 127 → no Snyk CLI: give the user the options the script printed (`SNYK_CLI` pointing at the CLI the VS Code
     extension downloaded, or installing it) and stop.
2. **Region / private Snyk:** if the user said their Snyk is in another region or on a private instance, add
   `--endpoint <url>` (they or their Snyk admin give the URL). Never guess one.
3. **Log in:** `bash toolkit/scripts/snyk-login.sh` (add the endpoint option if needed).
   - **Without** `SNYK_CLIENT_ID` / `SNYK_CLIENT_SECRET`, this is the **browser OAuth2 login**. Tell the user *before
     running it*: "A browser window will open: sign in with your company SSO, then come back." The command waits
     until they've signed in. Run it in a terminal the user can see. If the tool can't keep a command waiting,
     ask the user to run it themselves (`! bash toolkit/scripts/snyk-login.sh` in Claude Code, or in their terminal).
   - **With** both variables set, it's the **service-account (client credentials) login**: no browser.
     Never print, log or write the secret anywhere, and never ask the user to paste it into the chat.
4. **Result:** exit 0 → "Logged in as …", carry on with whatever needed the login. Exit 126 → the login didn't
   complete: say so, offer to try again, and suggest the user checks with their Snyk admin that SSO login is enabled.

## Rules

- The login is the user's own: never create, store or share credentials for them, and never commit anything from it.
- Don't run `--logout` unless the user asks.
