#!/bin/bash

echo "========================================="
echo "E-Learning Backend Setup Script"
echo "========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt ||
python3 -m pip install -r requirements.txt

# Navigate to main directory
cd main

# Run migrations
echo "Running migrations..."
python manage.py makemigrations
python manage.py migrate

# Create superuser prompt
echo ""
echo "Do you want to create a superuser? (y/n)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    python manage.py createsuperuser
fi

echo ""
echo "========================================="
echo "Setup complete!"
echo "========================================="
echo ""
echo "To start the server with WebSocket support:"
echo "  daphne -b 0.0.0.0 -p 8000 main.asgi:application"
echo ""
echo "Or use Django development server (no WebSocket):"
echo "  python manage.py runserver 0.0.0.0:8000"
echo ""
echo "Admin panel: http://localhost:8000/admin"
echo "API base URL: http://localhost:8000/api"
echo "========================================="
