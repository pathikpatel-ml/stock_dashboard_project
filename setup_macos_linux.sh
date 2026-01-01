#!/bin/bash

# Stock Dashboard - Quick Setup for macOS/Linux
# This script automates the setup process for Unix-like systems

set -e

echo ""
echo "============================================================"
echo "  Stock Dashboard - macOS/Linux Setup Script"
echo "============================================================"
echo ""

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3.10+ from https://www.python.org or your package manager"
    exit 1
fi

echo "Step 1: Checking Python version..."
python3 --version
echo ""

# Create virtual environment
echo "Step 2: Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    echo "Virtual environment created successfully."
fi
echo ""

# Activate virtual environment
echo "Step 3: Activating virtual environment..."
source venv/bin/activate
echo "Virtual environment activated."
echo ""

# Upgrade pip
echo "Step 4: Upgrading pip..."
python -m pip install --upgrade pip -q
echo "pip upgraded."
echo ""

# Install requirements
echo "Step 5: Installing dependencies..."
pip install -r requirements.txt -q
echo "Dependencies installed successfully."
echo ""

# Run verification
echo "Step 6: Verifying installation..."
python test_setup.py

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "  Setup Complete!"
    echo "============================================================"
    echo ""
    echo "Your virtual environment is ready to use."
    echo ""
    echo "Next steps:"
    echo "  1. Virtual environment is activated (venv is active)"
    echo "  2. Create .env file with NEWS_API_KEY if needed"
    echo "  3. Run: python run_dashboard_interactive_host.py"
    echo "  4. Open browser to: http://127.0.0.1:8050"
    echo ""
    echo "To deactivate virtual environment later, run: deactivate"
    echo ""
else
    echo ""
    echo "Warning: Some verification checks failed."
    echo "Please review the output above."
    echo ""
fi

exit 0
