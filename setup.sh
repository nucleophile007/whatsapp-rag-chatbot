#!/bin/bash

# Async RAG Quick Setup Script
# This script automates the initial setup process

set -e  # Exit on error

echo "=================================="
echo "🚀 Async RAG Quick Setup"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker is not running${NC}"
    echo "Please start Docker Desktop and try again."
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found${NC}"
    
    if [ -f .env.example ]; then
        echo "📄 Copying .env.example to .env..."
        cp .env.example .env
        echo -e "${GREEN}✅ Created .env file${NC}"
        echo ""
        echo -e "${YELLOW}⚠️  IMPORTANT: You need to add your Gemini API key!${NC}"
        echo ""
        echo "Steps:"
        echo "1. Get your API key from: https://aistudio.google.com/app/apikey"
        echo "2. Open .env file in your editor"
        echo "3. Replace 'your_gemini_api_key_here' with your actual key"
        echo ""
        read -p "Press Enter after you've updated the .env file..."
    else
        echo -e "${RED}❌ Error: .env.example not found${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Check if GOOGLE_API_KEY is set
if grep -q "your_gemini_api_key_here" .env 2>/dev/null; then
    echo -e "${RED}❌ Error: Please update GOOGLE_API_KEY in .env file${NC}"
    echo "Get your API key from: https://aistudio.google.com/app/apikey"
    exit 1
fi

echo -e "${GREEN}✅ GOOGLE_API_KEY is configured${NC}"
echo ""

# Stop existing containers if any
echo "🛑 Stopping existing containers (if any)..."
docker-compose down 2>/dev/null || true
echo ""

# Build and start services
echo "🔨 Building Docker images..."
docker-compose build

echo ""
echo "🚀 Starting all services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 5

# Check service status
echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "=================================="
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo "=================================="
echo ""
echo "🌐 Access Points:"
echo "   • FastAPI Server:  http://localhost:8000"
echo "   • Test Client:     http://localhost:8000/client"

echo "   • WAHA:           http://localhost:3000"
echo "   • Qdrant:         http://localhost:6333/dashboard"
echo ""
echo "📝 Next Steps:"
echo "   1. Test the API:"
echo "      curl -X POST http://localhost:8000/chat \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"query\":\"Hello\",\"client_id\":\"test\"}'"
echo ""
echo "   2. Or open the web client:"
echo "      open http://localhost:8000/client"
echo ""
echo "   3. For WhatsApp integration:"
echo "      - Configure WAHA and scan QR code at http://localhost:3000"
echo ""
echo "📚 Documentation: See README.md for detailed setup"
echo ""
echo "🔍 View logs:"
echo "   docker-compose logs -f"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose down"
echo ""
