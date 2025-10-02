#!/usr/bin/env bash
set -e

echo "==============================="
echo "🔹 CI/CD Local Sanity Check"
echo "==============================="

echo "👉 Checking Python & dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "👉 Running lint checks..."
python -m flake8 src tests

echo "👉 Running unit tests..."
python -m pytest

# 5. Build Docker image
echo "👉 Building Docker image..."
docker build -t fintech-reconciliation:local .

# 6. Verify Docker run works
echo "👉 Running container sanity check..."
docker run --rm fintech-reconciliation:local python -c "import src.main"

# 7. Confirm reports folder
echo "👉 Checking reports folder..."
if [ -d "Local_file" ]; then
  echo "✅ Reports directory exists"
else
  echo "⚠️ Reports directory missing, run your app to generate reports"
fi

echo "==============================="
echo "✅ All major CI/CD checks passed locally!"
echo "==============================="
