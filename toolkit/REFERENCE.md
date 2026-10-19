# Reference: folders and scripts

Read this only when you need a script that isn't spelled out in the phase file you're running.

## Layout (paths relative to the project root)

| Path | What |
|------|------|
| `repos/repos.txt` | Target repos, by git URL: `<name> <git-url> [branch=] [path=] [smoke=true] [build="..."]` |
| `repos/<name>/` (`repo_dir`) | The repo's clone (git-ignored). **All code changes happen here**, on the workflow's branch `deps/<id>`. Build dir = `<repo_dir>/<path>`. The user's own checkouts elsewhere are never touched |
| `workflows/wf-<NNN>-<slug>/` | One folder per upgrade: `STATUS.md` + the numbered docs + raw data |
| `workflows/<id>/repos.txt` | Optional: limit this upgrade to some repos (same format) |
| `toolkit/phases/`, `roles/`, `templates/`, `scripts/` | Procedures, subagent definitions, doc templates, tools |

Scripts (run from the project root, Python with `python3 -I`):

| Script | Purpose |
|--------|---------|
| `toolkit/scripts/repos.py add\|ensure\|clone\|list\|status\|release` | Manage target repos. `--workflow <id> clone` puts each clone on `deps/<id>`. `list` gives `name, build_dir, verify_args, url, base_branch, repo_dir` as TSV |
| `toolkit/scripts/snyk-scan.sh <out> [--manifest f] [snyk args]` | `snyk test --all-projects --json` for every repo folder |
| `toolkit/scripts/parse-snyk.py <json…> --md --csv --json` | Every flagged package + changes grouped by the dependency you edit |
| `toolkit/scripts/maven-facts.sh <build_dir> <out> [filters]` | Parent, declared deps, version properties, resolved tree |
| `toolkit/scripts/verify-repo.sh` / `.ps1` `<build_dir> <out> [--smoke] [--build-cmd]` | Build → JUnit counts → smoke boot → `summary.json` |

The manifest for an upgrade is `workflows/<id>/repos.txt` if it exists, else `repos/repos.txt`. Pass it with
`--manifest` to `repos.py` and `snyk-scan.sh`.

