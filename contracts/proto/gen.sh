#!/usr/bin/env bash
# Генерация Python gRPC stubs из .proto.
# Запускается из корня репо: ./contracts/proto/gen.sh
#
# Source: contracts/proto/auth/v1/auth.proto
# Targets:
#   backend/auth-service/generated/grpc_pb/
#   backend/tasks-service/generated/grpc_pb/
# (architecture.md §5.4.4 — committed в репо).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROTO_DIR="$REPO_ROOT/contracts/proto"
TARGETS=(
  "$REPO_ROOT/backend/auth-service/src/auth_service/generated"
  "$REPO_ROOT/backend/tasks-service/src/tasks_service/generated"
)

for target in "${TARGETS[@]}"; do
  mkdir -p "$target"
  : > "$target/__init__.py"
  (
    cd "$PROTO_DIR" && \
    uv run python -m grpc_tools.protoc \
      -I. \
      --python_out="$target" \
      --grpc_python_out="$target" \
      --mypy_out="$target" \
      --mypy_grpc_out="$target" \
      auth/v1/auth.proto
  )

  # Создаём __init__.py для пакетной структуры auth/v1/.
  find "$target" -type d -exec touch {}/__init__.py \;
done

echo "Generated:"
for target in "${TARGETS[@]}"; do
  find "$target" -name "*.py" -o -name "*.pyi" | sort
done
