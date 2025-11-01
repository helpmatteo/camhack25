#!/bin/bash
# Startup script for camcam project

echo "🚀 Starting camcam..."
echo ""

# Start backend
echo "📡 Starting backend server..."
cd backend
python run.py &
BACKEND_PID=$!

# Wait a moment for backend to start and write .env.local
sleep 2

# Start frontend
echo ""
echo "🎨 Starting frontend..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both servers are starting!"
echo "   Backend PID: $BACKEND_PID"
echo "   Frontend PID: $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop both servers"

# Trap Ctrl+C and kill both processes
trap "echo ''; echo '🛑 Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT

# Wait for both processes
wait

