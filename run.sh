#!/bin/bash
# HomeAI Backend Runner

# Check for .env
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "   Copy .env.example to .env and configure it."
    exit 1
fi

# Check SECRET_KEY
if grep -q "your-secret-key-here" .env 2>/dev/null; then
    echo "❌ SECRET_KEY not configured in .env!"
    echo "   Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    exit 1
fi

# Run
echo "🚀 Starting HomeAI Backend..."
python main.py
