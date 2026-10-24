#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-x86_64-unknown-linux-gnu}"
case "$TARGET" in
  x86_64-unknown-linux-gnu) PLATFORM="linux/amd64" ;;
  aarch64-unknown-linux-gnu) PLATFORM="linux/arm64" ;;
  *) echo "unsupported Linux target: $TARGET (supported: x86_64-unknown-linux-gnu, aarch64-unknown-linux-gnu)" >&2; exit 2 ;;
esac
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker buildx build --platform "$PLATFORM" -f engine/Dockerfile --output type=local,dest=.build/engine .
mkdir -p .build/cargo
docker run --rm --platform "$PLATFORM" \
  -v "$ROOT:/work" -v "${LINUX_CARGO_CACHE:-$ROOT/.build/cargo}:/cache" \
  -e CARGO_HOME=/cache -e MEOW_ENGINE_BINARY=/work/.build/engine/meow-engine \
  -e CARGO_TARGET_DIR=/work/.build/linux-target -w /work rust:1.97-slim-bookworm \
  sh -c 'cargo test --locked --features bundled-engine --manifest-path backend/Cargo.toml && cargo build --locked --release --features bundled-engine --manifest-path backend/Cargo.toml'
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
"${CPR_PLUGIN_BIN:-cpr-plugin}" package --manifest "$ROOT/plugin.json" \
  --binary "$ROOT/.build/linux-target/release/codex-model-health-plugin" \
  --target "$TARGET" --resource-map web=frontend/dist \
  --resource-map legal=. --resource-map engine-legal=.build/engine --output-dir "$ROOT/dist"
VERSION="$(node -p "require('./plugin.json').version")"
SMOKE_PLATFORM="$PLATFORM" python3 scripts/package-smoke.py "$ROOT/dist/local.model-health-$VERSION-$TARGET.tar.gz" --continuous --modeltrace --updates
