#!/bin/bash
# Run frontend code quality checks
set -e

cd "$(dirname "$0")/frontend"

echo "Running Prettier format check..."
npx prettier --check .

echo ""
echo "All frontend quality checks passed."
