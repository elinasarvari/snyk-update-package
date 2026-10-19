# /dep-save: push a workflow's records to this project's repository

Commits one workflow's folder (`workflows/wf-NNN-…/`), plus `workflows/INDEX.md` and the research cache, and pushes
it to `snyk-update-package`'s own remote, so the documentation is on GitHub instead of only on one machine.
`/dep-run` and every step also do this by themselves when they finish.

## Steps

1. Resolve the workflow (`1`, `wf-001`, or the folder). If the user gave none, use the one just worked on, or ask.
2. Run `python3 -I toolkit/scripts/workflows.py save <id>`.
   - It commits **only** that workflow's records, never other files, and leaves out raw Snyk JSON, logs and error
     files (`.gitignore`). If GitHub has newer records, it rebases first. Conflicts in the generated `INDEX.md` are
     rebuilt automatically.
   - **`REFUSED: this repository is PUBLIC`** → tell the user why (records name their repos and open
     vulnerabilities) and how to make it private (GitHub → Settings → General → Danger Zone → Change visibility).
     Only add `--allow-public` if the user explicitly says publishing is intended.
   - Push rejected or a real conflict → show the message; don't force-push, don't discard anything.
3. Reply with what was pushed (the folder and the commit message), or why not.

## Rules

- Never `git push --force`, never commit files outside `workflows/`, never commit the clones under `repos/`.
- This pushes **this project's** repository only. Changes to the target repos go through `/dep-publish`.
