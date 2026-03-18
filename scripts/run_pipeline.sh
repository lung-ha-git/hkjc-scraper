#!/bin/bash
# HKJC Pipeline Runner Wrapper

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# Load dev environment
export MONGODB_DB_NAME=hkjc_racing_dev

# Run the pipeline
python3 -m src.pipeline.runner "$@"
