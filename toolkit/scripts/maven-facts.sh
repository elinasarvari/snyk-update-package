#!/usr/bin/env bash
# Collect the dependency facts the inventory/analysis phases need from one Maven repo.
# Read-only: does not modify the repo (writes only into <out-dir>).
#
# Usage: maven-facts.sh <repo-dir> <out-dir> [artifact-filter ...]
#   artifact-filter  optional substrings (e.g. spring-boot camel) - matching lines from
#                    the resolved tree are copied into filtered-tree.txt
#
# Outputs in <out-dir>:
#   facts.env          PARENT / JAVA_VERSION / BUILD_TOOL / GIT_BRANCH / GIT_COMMIT
#   dependency-tree.txt full resolved tree (all modules)
#   filtered-tree.txt   tree lines matching the filters, with module headers
#   declared.txt        <groupId>:<artifactId>:<version> as written in each pom.xml
#   version-props.txt   <properties> entries ending in .version (the usual override knobs)
set -uo pipefail

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

{
  echo "BUILD_TOOL=maven ($MVN)"
  echo "PARENT=$(eval_expr project.parent.groupId):$(eval_expr project.parent.artifactId):$(eval_expr project.parent.version)"
  # Read from the pom: help:evaluate returns the JVM's java.version system property instead.
  echo "PROJECT_JAVA=$(grep -m1 -o '<java.version>[^<]*' pom.xml | sed 's/<java.version>//')"
  echo "JVM=$(java -version 2>&1 | head -1)"
  echo "GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo "GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null)"
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
  pattern=$(IFS='|'; echo "$*")
  # Module header lines start without whitespace/tree glyphs; keep them for context.
  grep -E "^[a-zA-Z]|$pattern" "$out/dependency-tree.txt" > "$out/filtered-tree.txt"
fi

: > "$out/declared.txt"
: > "$out/version-props.txt"
while IFS= read -r pom; do
  python3 -I - "$pom" >> "$out/declared.txt" 2>/dev/null <<'PY'
import sys, xml.etree.ElementTree as ET
pom = sys.argv[1]
ns = {"m": "http://maven.apache.org/POM/4.0.0"}
root = ET.parse(pom).getroot()
def text(el, tag):
    found = el.find("m:" + tag, ns)
    return found.text.strip() if found is not None and found.text else ""
parent = root.find("m:parent", ns)
if parent is not None:
    print("%s\tparent\t%s:%s:%s" % (pom, text(parent, "groupId"), text(parent, "artifactId"), text(parent, "version")))
for section, xpath in (("managed", "m:dependencyManagement/m:dependencies/m:dependency"),
                       ("dependency", "m:dependencies/m:dependency"),
                       ("plugin", "m:build/m:plugins/m:plugin")):
    for dep in root.findall(xpath, ns):
        print("%s\t%s\t%s:%s:%s%s" % (pom, section, text(dep, "groupId"), text(dep, "artifactId"),
              text(dep, "version") or "(managed)", " scope=" + text(dep, "scope") if text(dep, "scope") else ""))
PY
  sed -n '/<properties>/,/<\/properties>/p' "$pom" | grep -E '\.version>' \
    | sed -e 's/^[[:space:]]*//' -e "s|^|$pom: |" >> "$out/version-props.txt"
done < <(find . -name pom.xml -not -path '*/target/*' -not -path '*/node_modules/*')

cat "$out/facts.env"
echo "declared deps: $(wc -l < "$out/declared.txt" | tr -d ' ')  tree lines: $(wc -l < "$out/dependency-tree.txt" 2>/dev/null | tr -d ' ')"
