@echo off
echo Starting Backend...
start cmd /k "python backend/server.py"
echo Starting Frontend...
cd frontend
start cmd /k "npm run dev"
echo Done! App should be running at http://localhost:5173
pause
