#!/bin/bash

# Metal Trend Analysis Tool - Quick Start Script

echo "======================================"
echo "  Metal Trend Analysis Tool - Quick Start"
echo "======================================"
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Current Python version: $python_version"
echo ""

# Check virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created"
    echo ""
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "Virtual environment activated"
echo ""

# Check dependencies
echo "Checking dependencies..."
pip install -r requirements.txt
echo "Dependencies installed"
echo ""

# Check configuration file
if [ ! -f "config/config.yaml" ]; then
    echo "Warning: config/config.yaml does not exist"
    echo "Please copy config/config.yaml.example and add your API keys"
    echo ""
    exit 1
fi

# Check environment variables
if [ ! -f ".env" ]; then
    echo "Warning: .env file does not exist"
    echo "Please copy .env.example and add your API keys"
    echo ""
    echo "Create .env file now? (y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        cp .env.example .env
        echo ".env file created, please edit and add your API keys"
        echo ""
        exit 1
    else
        exit 1
    fi
fi

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "Environment variables loaded"
    echo ""
fi

# Run program
echo "Starting analysis program..."
echo ""
python src/main.py "$@"

echo ""
echo "Analysis complete!"
