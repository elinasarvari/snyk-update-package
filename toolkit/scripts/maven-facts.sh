#!/usr/bin/env bash
# Collect the dependency facts the inventory/analysis phases need from one Maven repo.
# Read-only: does not modify the repo (writes only into <out-dir>).
# Windows/PowerShell twin: maven-facts.ps1 (same arguments, same output). Parsing lives in script-helpers.py.
#
# Usage: maven-facts.sh <repo-dir> <out-dir> [artifact-filter ...]
#   artifact-filter  optional substrings (e.g. spring-boot camel) - matching lines from
#                    the resolved tree are copied into filtered-tree.txt
#
# Outputs in <out-dir>:
#   facts.env          BUILD_TOOL / PARENT / PROJECT_JAVA / JVM / GIT_BRANCH / GIT_COMMIT / GIT_DIRTY
#   dependency-tree.txt full resolved tree (all modules)
#   filtered-tree.txt   tree lines matching the filters, with module headers
#   declared.txt        <groupId>:<artifactId>:<version> as written in each pom.xml
#   version-props.txt   <properties> entries ending in .version (the usual override knobs)
set -uo pipefail

helpers="$(cd "$(dirname "$0")" && pwd)/script-helpers.py"
py() { python3 -I "$helpers" "$@"; }

repo=${1:?repo dir required}
out=${2:?out dir required}
shift 2
mkdir -p "$out"
out=$(cd "$out" && pwd)
cd "$repo" || { echo "cannot cd to $repo" >&2; exit 2; }

if [[ ! -f pom.xml ]]; then
  echo "BUILD_TOOL=unsupported" > "$out/facts.env"
  echo "No pom.xml in $repo - this script only handles Maven. Gradle: run './gradlew dependencies'." >&2
  exit 3
fi

if [[ -x ./mvnw ]]; then MVN=./mvnw; else MVN=mvn; fi

eval_expr() { $MVN -q -N help:evaluate -Dexpression="$1" -DforceStdout 2>/dev/null; }
env_json=$(py env-info)
field() { python3 -I -c "import json,sys;print(json.load(sys.stdin)['$1'])" <<< "$env_json"; }

{
  echo "BUILD_TOOL=maven ($MVN)"
  echo "PARENT=$(eval_expr project.parent.groupId):$(eval_expr project.parent.artifactId):$(eval_expr project.parent.version)"
  # Read from the pom: help:evaluate returns the JVM's java.version system property instead.
  echo "PROJECT_JAVA=$(py project-java pom.xml)"
  echo "JVM=$(field java)"
  echo "GIT_BRANCH=$(field branch)"
  echo "GIT_COMMIT=$(field commit)"
  echo "GIT_DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ') files"
} > "$out/facts.env"

# appendOutput keeps every module's tree in a multi-module build.
rm -f "$out/dependency-tree.txt"
if ! $MVN -q dependency:tree -DoutputFile="$out/dependency-tree.txt" -DappendOutput=true \
      > "$out/dependency-tree.log" 2>&1; then
  echo "dependency:tree failed - see $out/dependency-tree.log" >&2
fi

: > "$out/filtered-tree.txt"
if [[ $# -gt 0 && -f "$out/dependency-tree.txt" ]]; then
  py filter-tree "$out/dependency-tree.txt" "$out/filtered-tree.txt" "$@"
fi

: > "$out/declared.txt"
: > "$out/version-props.txt"
while IFS= read -r pom; do
  py pom-declared "$pom" >> "$out/declared.txt" 2>/dev/null
  py version-props "$pom" >> "$out/version-props.txt" 2>/dev/null
done < <(py find-poms)          # skips target/, node_modules/, .git/ ... (toolkit/ignore-dirs.txt)

cat "$out/facts.env"
echo "declared deps: $(wc -l < "$out/declared.txt" | tr -d ' ')  tree lines: $(wc -l < "$out/dependency-tree.txt" 2>/dev/null | tr -d ' ')"
