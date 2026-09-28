#!/bin/bash
set -e

echo "=== Nova Platform Setup ==="

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Copy env file if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env file — add your OPENAI_API_KEY"
fi

# Initialize database
echo "Initializing database..."
python3 -c "from storage.database import init_db; init_db()"

echo ""
echo "=== Setup Complete ==="
echo "1. Add your OPENAI_API_KEY to .env"
echo "2. Run the API:  python3 -m uvicorn api.server:app --reload --port 8000"
echo "3. Run the UI:   streamlit run ui/app.py --server.port 8501"
