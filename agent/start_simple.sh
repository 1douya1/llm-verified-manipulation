#!/bin/bash

echo "🤖 Launching Robot Control Center - Simple Version"
echo "================================================"

# Ensure we are in the correct directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📍 Current working directory: $(pwd)"
echo "📋 Checking required files..."

# Check required files exist
if [ ! -f "simple_backend.py" ]; then
    echo "❌ Error: simple_backend.py does not exist"
    exit 1
fi

if [ ! -f "simple_frontend.html" ]; then
    echo "❌ Error: simple_frontend.html does not exist"
    exit 1
fi

echo "✅ All required files are present"

# Check Python dependencies
echo ""
echo "📦 Checking Python dependencies..."
python3 -c "import fastapi, uvicorn, websockets" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Missing dependencies, installing..."
    pip install fastapi uvicorn[standard] websockets pydantic anyio
    echo "✅ Dependencies installed"
else
    echo "✅ Python dependencies satisfied"
fi

# Check ports and clean up
echo ""
echo "🔍 Checking ports..."
PORT_8000=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$PORT_8000" ]; then
    echo "⚠️  Port 8000 is in use (PID: $PORT_8000), stopping..."
    kill $PORT_8000 2>/dev/null
    sleep 2
    echo "✅ Port 8000 freed"
fi

PORT_3000=$(lsof -ti:3000 2>/dev/null)
if [ ! -z "$PORT_3000" ]; then
    echo "⚠️  Port 3000 is in use (PID: $PORT_3000), stopping..."
    kill $PORT_3000 2>/dev/null
    sleep 2
    echo "✅ Port 3000 freed"
fi

echo ""
echo "🚀 Starting services..."
echo "================================================"

# Start frontend HTTP server (in background)
echo "1️⃣  Start frontend HTTP server (port 3000)..."
python3 -m http.server 3000 >/dev/null 2>&1 &
HTTP_PID=$!
sleep 1

if kill -0 $HTTP_PID 2>/dev/null; then
    echo "✅ Frontend server started (PID: $HTTP_PID)"
else
    echo "❌ Frontend server failed to start"
    exit 1
fi

echo ""
echo "2️⃣  Start backend Agent server (port 8000)..."
echo "   (This may take 1-2 minutes to initialize the Agent and load MCP tools)"
echo ""

# Start backend (foreground so we can see logs)
echo "🔧 Backend server is starting..."
echo "================================================"

# Define cleanup function
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    if [ ! -z "$HTTP_PID" ]; then
        kill $HTTP_PID 2>/dev/null
        echo "✅ Frontend server stopped"
    fi
    
    # Stop possible backend process
    BACKEND_PID=$(lsof -ti:8000 2>/dev/null)
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null
        echo "✅ Backend server stopped"
    fi
    
    echo "🧹 Cleanup done"
    exit 0
}

# Catch Ctrl+C signal
trap cleanup INT TERM

# Start backend (run in background to allow readiness loop)
python3 simple_backend.py &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend server to start..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/status >/dev/null 2>&1; then
        echo "✅ Backend server started!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Backend server startup timed out"
        cleanup
        exit 1
    fi
    sleep 1
    echo -n "."
done

echo ""
echo "🎉 System startup complete!"
echo "================================================"
echo ""
echo "📱 Please follow these steps:"
echo ""
echo "1️⃣  Open in your browser:"
echo "    👉 http://localhost:3000/simple_frontend.html"
echo ""
echo "2️⃣  Wait until the page shows 'System Ready' (usually 1-2 minutes)"
echo "    - You'll first see 'Connecting to Agent, please wait...'"
echo "    - Once the Agent is initialized, it will show 'System Ready'"
echo "    - A green dot and tool count will appear in the top-right"
echo ""
echo "3️⃣  Start chatting with the robot!"
echo "    - Type commands or click quick command buttons"
echo "    - For example: 'Check system status' or 'Setup planning scene'"
echo ""
echo "🔧 Other useful links:"
echo "    - API Docs: http://localhost:8000/docs"
echo "    - System Status: http://localhost:8000/api/status"
echo ""
echo "❗ Important notes:"
echo "    - Ensure your MCP server is running"
echo "    - Ensure the Anthropic API Key is correctly set"
echo "    - Press Ctrl+C to stop all services"
echo ""
echo "================================================"
echo "🖥️  Backend logs (Agent initialization info):"
echo "================================================"

# Wait for backend process (to show logs)
wait $BACKEND_PID 