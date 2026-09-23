#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
python_bin="${PYTHON_BIN:-python}"
cd "$repo_root/packages/rpc-contracts"
"$python_bin" -m grpc_tools.protoc \
  -I proto -I "$repo_root/services/management-java/proto" \
  --python_out=src --grpc_python_out=src \
  --mypy_out=src --mypy_grpc_out=src \
  a2flow/content/v1/content.proto
# The descriptor includes the exact shared identity contract, not a handwritten copy.
if [[ -n "${DESCRIPTOR_OUTPUT:-}" ]]; then
  "$python_bin" -m grpc_tools.protoc \
    -I proto -I "$repo_root/services/management-java/proto" \
    --include_imports --descriptor_set_out="$DESCRIPTOR_OUTPUT" \
    a2flow/content/v1/content.proto
fi
