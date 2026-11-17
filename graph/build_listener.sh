#!/usr/bin/env bash
# Compile TraceDump.java against your jpf-core and pack it into build/TraceDump.jar
# Usage:  ./build_listener.sh /path/to/jpf-core
#         (optional)  JAVA8_HOME=/path/to/jdk8 ./build_listener.sh /path/to/jpf-core
set -euo pipefail

JPF_CORE="${1:-${JPF_CORE:-}}"
if [ -z "$JPF_CORE" ] || [ ! -f "$JPF_CORE/build/jpf.jar" ]; then
  echo "Give the path to jpf-core (must contain build/jpf.jar):  ./build_listener.sh /path/to/jpf-core" >&2
  exit 1
fi

BIN=""
if [ -n "${JAVA8_HOME:-}" ]; then BIN="$JAVA8_HOME/bin/"; fi

cd "$(dirname "$0")"
rm -rf build && mkdir -p build
"${BIN}javac" -source 8 -target 8 -nowarn -cp "$JPF_CORE/build/jpf.jar" -d build TraceDump.java
(cd build && "${BIN}jar" cf TraceDump.jar TraceDump*.class)
echo "built: $(pwd)/build/TraceDump.jar"
