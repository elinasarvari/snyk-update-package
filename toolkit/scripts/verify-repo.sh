#!/usr/bin/env bash
# Build, test and (optionally) boot one repository, writing a machine-readable summary.
# Windows/PowerShell twin: verify-repo.ps1 (same arguments, same output). Parsing lives in script-helpers.py.
#
# Usage: verify-repo.sh <repo-dir> <out-dir> [--smoke] [--build-cmd "<cmd>"]
#   --smoke       (Spring Boot apps only) after a green build, start the packaged jar on a random port and wait
#                 for Spring Boot's "Started ... in" line (catches startup-only failures
#                 like Boot/Camel version mismatches that unit tests can miss)
#   --build-cmd   override the auto-detected build command
#
# Outputs in <out-dir>: build.log, smoke.log, summary.json - nothing is written into the repo itself.
# The smoke boot runs with <out-dir> as its working folder, so files an app writes at runtime (logs, local
# databases) land there, not in the repo. Any file the build leaves in the repo that git doesn't ignore is
# reported in summary.json as "left_in_repo" (it is never deleted).
# Exit code: 0 all green, 1 build/tests failed, 2 smoke failed, 3 unsupported repo
set -uo pipefail

helpers="$(cd "$(dirname "$0")" && pwd)/script-helpers.py"
py() { python3 -I "$helpers" "$@"; }

repo=${1:?repo dir required}
out=${2:?out dir required}
shift 2
smoke=false
build_cmd=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) smoke=true ;;
    --build-cmd) build_cmd=$2; shift ;;
    *) echo "unknown arg $1" >&2; exit 64 ;;
  esac
  shift
done

mkdir -p "$out"
out=$(cd "$out" && pwd)
cd "$repo" || { echo "cannot cd to $repo" >&2; exit 3; }
repo=$(pwd)

if [[ -z "$build_cmd" ]]; then
  if [[ -f pom.xml ]]; then
    if [[ -x ./mvnw ]]; then build_cmd="./mvnw -B clean verify"; else build_cmd="mvn -B clean verify"; fi
  elif ls build.gradle* >/dev/null 2>&1; then
    if [[ -x ./gradlew ]]; then build_cmd="./gradlew clean build"; else build_cmd="gradle clean build"; fi
  else
    py summary "$out/summary.json" "repo=$repo" "status=unsupported" >/dev/null
    echo "No pom.xml or build.gradle in $repo" >&2
    exit 3
  fi
fi

py git-snapshot "$out/.before-build.json"     # to spot anything the build adds to the repo

start=$(date +%s)
bash -c "$build_cmd" > "$out/build.log" 2>&1
build_exit=$?
duration=$(( $(date +%s) - start ))

# Count test results from JUnit XML - every module's reports (multi-module builds included).
tests_json=$(py junit)

smoke_status="skipped"
if $smoke && [[ $build_exit -eq 0 ]]; then
  jar=$(ls target/*.jar build/libs/*.jar 2>/dev/null | grep -vE -- '-(plain|sources|javadoc|tests)\.jar$' | head -1)
  if [[ -z "$jar" ]]; then
    smoke_status="no-jar"
  else
    jar=$(cd "$(dirname "$jar")" && pwd)/$(basename "$jar")
    (cd "$out" && exec java -jar "$jar" --server.port=0) > "$out/smoke.log" 2>&1 &
    pid=$!
    smoke_status="timeout"
    for _ in $(seq 1 90); do
      if grep -qE 'Started [A-Za-z0-9_$]+ in' "$out/smoke.log"; then smoke_status="started"; break; fi
      if grep -q 'APPLICATION FAILED TO START' "$out/smoke.log" || ! kill -0 "$pid" 2>/dev/null; then
        smoke_status="failed"; break
      fi
      sleep 1
    done
    kill "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
  fi
fi

left_in_repo=$(py left-in-repo "$out/.before-build.json")
rm -f "$out/.before-build.json"

status="green"
exit_code=0
if [[ $build_exit -ne 0 ]]; then status="build-failed"; exit_code=1
elif [[ "$smoke_status" == "failed" || "$smoke_status" == "timeout" || "$smoke_status" == "no-jar" ]]; then status="smoke-failed"; exit_code=2
fi

py summary "$out/summary.json" --env "repo=$repo" "build_cmd=$build_cmd" "build_exit:=$build_exit" "duration_s:=$duration" "tests:=$tests_json" \
  "smoke=$smoke_status" "left_in_repo:=$left_in_repo" "status=$status"

if [[ "$left_in_repo" != "[]" ]]; then
  echo "--- WARNING: the build left files in the repo that git doesn't ignore: $left_in_repo"
fi
if [[ $build_exit -ne 0 ]]; then
  echo "--- first errors from build.log ---"
  py first-errors "$out/build.log" 40
fi
exit $exit_code
