"""snyk-login.sh / snyk-login.ps1 - OAuth2 login without clicking in the VS Code extension.

A fake `snyk` keeps a logged-in/out state file, so every path can be checked: browser OAuth, client
credentials (service account), already logged in, --status, --logout, --endpoint, and that a failed login
or a scan without a login is reported. The client secret must never appear in the output.
"""
import os

from helpers import BashScripts, PowerShellScripts, Sandbox

FAKE = """import os, sys
state, log = %(state)r, %(log)r
args = sys.argv[1:]
with open(log, "a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\\n")
env_token = os.environ.get("SNYK_OAUTH_TOKEN") or os.environ.get("SNYK_TOKEN")
# like the real CLI: a token in the environment is used instead of the stored login
logged_in = (env_token == "valid-token") if env_token else os.path.exists(state)
if args[:1] == ["whoami"]:
    print("sso-user@acme.example") if logged_in else None
    sys.exit(0 if logged_in else 2)
if args[:1] == ["auth"]:
    if %(auth_works)r:
        open(state, "w").write("ok")
        print("Your account has been authenticated.")
        sys.exit(0)
    print("Authentication failed")
    sys.exit(2)
if args[:1] == ["logout"]:
    if logged_in:
        os.remove(state)
    sys.exit(0)
if args[:1] == ["config"]:
    sys.exit(0)
print("[]")
sys.exit(0)
"""

SECRET = "s3cr3t-value-never-print-me"


class SnykLoginTests:
    def fake_cli(self, logged_in=False, auth_works=True):
        self.state = os.path.join(self.tmp, "snyk-state")
        self.log = os.path.join(self.tmp, "snyk-calls.log")
        if logged_in:
            self.write(self.state, "ok")
        cli = self.make_tool(os.path.join(self.tmp, "bin", "snyk"),
                             FAKE % {"state": self.state, "log": self.log, "auth_works": auth_works})
        return dict(self.env, SNYK_CLI=cli)

    def calls(self):
        return self.read(self.log).splitlines() if os.path.exists(self.log) else []

    def auth_calls(self):
        return [c for c in self.calls() if c.startswith("auth")]

    def test_browser_oauth_login_when_logged_out(self):
        env = self.fake_cli()
        proc = self.script("snyk-login.sh", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(self.auth_calls(), ["auth --auth-type=oauth"], "OAuth2 browser flow, explicitly")
        self.assertIn("Opening your browser", proc.stdout)
        self.assertIn("Logged in to Snyk as sso-user@acme.example", proc.stdout)

    def test_already_logged_in_does_nothing(self):
        env = self.fake_cli(logged_in=True)
        proc = self.script("snyk-login.sh", env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Already logged in to Snyk as sso-user@acme.example", proc.stdout)
        self.assertEqual(self.auth_calls(), [], "no browser pops up when there's nothing to do")

    def test_force_logs_in_again(self):
        env = self.fake_cli(logged_in=True)
        self.script("snyk-login.sh", "--force", env=env, check=True)
        self.assertEqual(self.auth_calls(), ["auth --auth-type=oauth"])

    def test_client_credentials_login_without_a_browser_never_prints_the_secret(self):
        temp = os.path.join(self.tmp, "system-temp")          # where any temporary script would land
        os.makedirs(temp)
        env = dict(self.fake_cli(), SNYK_CLIENT_ID="svc-acct-123", SNYK_CLIENT_SECRET=SECRET,
                   TMPDIR=temp, TEMP=temp, TMP=temp)
        proc = self.script("snyk-login.sh", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(self.auth_calls(),
                         ["auth --auth-type=oauth --client-id=svc-acct-123 --client-secret=%s" % SECRET])
        self.assertNotIn(SECRET, proc.stdout, "the secret must never be printed")
        self.assertNotIn("Opening your browser", proc.stdout)
        for name in os.listdir(temp):                         # nothing on disk may hold the secret
            path = os.path.join(temp, name)
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    self.assertNotIn(SECRET, fh.read(), name)

    def test_browser_option_wins_over_client_credentials(self):
        env = dict(self.fake_cli(), SNYK_CLIENT_ID="svc-acct-123", SNYK_CLIENT_SECRET=SECRET)
        self.script("snyk-login.sh", "--browser", env=env, check=True)
        self.assertEqual(self.auth_calls(), ["auth --auth-type=oauth"])

    def test_client_credentials_option_without_credentials_is_an_error(self):
        env = self.fake_cli()
        proc = self.script("snyk-login.sh", "--client-credentials", env=env)
        self.assertEqual(proc.returncode, 64)
        self.assertIn("SNYK_CLIENT_ID and SNYK_CLIENT_SECRET", proc.stdout)
        self.assertEqual(self.auth_calls(), [])

    def test_failed_login_is_reported(self):
        env = self.fake_cli(auth_works=False)
        proc = self.script("snyk-login.sh", env=env)
        self.assertEqual(proc.returncode, 126)
        self.assertIn("Snyk login did not complete", proc.stdout)

    def test_status_reports_without_logging_in(self):
        env = self.fake_cli()
        proc = self.script("snyk-login.sh", "--status", env=env)
        self.assertEqual(proc.returncode, 126)
        self.assertIn("Not logged in to Snyk", proc.stdout)
        self.assertEqual(self.auth_calls(), [])
        self.write(self.state, "ok")
        proc = self.script("snyk-login.sh", "--status", env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Logged in to Snyk as sso-user@acme.example", proc.stdout)

    def test_logout(self):
        env = self.fake_cli(logged_in=True)
        self.script("snyk-login.sh", "--logout", env=env, check=True)
        self.assertFalse(os.path.exists(self.state))
        self.assertEqual(self.script("snyk-login.sh", "--status", env=env).returncode, 126)

    def test_endpoint_is_set_before_logging_in(self):
        env = self.fake_cli()
        proc = self.script("snyk-login.sh", "--endpoint", "https://api.eu.snyk.io", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        calls = self.calls()
        self.assertIn("config set endpoint=https://api.eu.snyk.io", calls)
        self.assertLess(calls.index("config set endpoint=https://api.eu.snyk.io"), calls.index("auth --auth-type=oauth"))

    def test_unknown_option_and_missing_cli(self):
        env = self.fake_cli()
        self.assertEqual(self.script("snyk-login.sh", "--colour", env=env).returncode, 64)
        env_without = dict(self.env, SNYK_CLI=os.path.join(self.tmp, "nope", "snyk"))
        self.assertEqual(self.script("snyk-login.sh", env=env_without).returncode, 127)

    def test_scan_without_login_points_to_the_login_script(self):
        self.manifest()
        proc = self.script("snyk-scan.sh", "out", env=self.fake_cli())
        self.assertEqual(proc.returncode, 126)
        self.assertIn("snyk-login", proc.stdout)
        self.assertIn("opens your browser", proc.stdout)

    def test_a_valid_token_in_the_environment_is_checked_with_snyk_and_accepted(self):
        env = dict(self.fake_cli(), SNYK_OAUTH_TOKEN="valid-token")
        proc = self.script("snyk-login.sh", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Already logged in to Snyk as sso-user@acme.example", proc.stdout)
        self.assertIn("whoami --experimental", self.calls(), "asked Snyk, didn't assume")
        self.assertEqual(self.auth_calls(), [])

    def test_a_bad_token_in_the_environment_is_not_trusted(self):
        for var in ("SNYK_TOKEN", "SNYK_OAUTH_TOKEN"):
            env = dict(self.fake_cli(logged_in=True), **{var: "expired-or-wrong-region"})
            proc = self.script("snyk-login.sh", "--status", env=env)
            self.assertEqual(proc.returncode, 126, "%s: a set-but-rejected token must not count as logged in" % var)
            self.manifest()
            scan = self.script("snyk-scan.sh", "out", env=env)
            self.assertEqual(scan.returncode, 126, "%s: the scan must stop before scanning" % var)
            login = self.script("snyk-login.sh", env=env)
            self.assertEqual(login.returncode, 126)
            self.assertIn("Snyk rejects it", login.stdout)


class SnykLoginBash(BashScripts, SnykLoginTests, Sandbox):
    pass


class SnykLoginPowerShell(PowerShellScripts, SnykLoginTests, Sandbox):
    pass
