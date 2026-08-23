@echo off
echo ╔══════════════════════════════════════════╗
echo ║   AURA-PI Setup — Windows Dev Mode     ║
echo ╚══════════════════════════════════════════╝

echo.
echo [1/4] Creating Python virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

echo [2/4] Installing Python packages...
pip install --upgrade pip
pip install flask flask-socketio eventlet ollama requests pillow python-dotenv
pip install opencv-python numpy pydantic aiofiles
REM Note: vosk and pyaudio require manual install on Windows
REM Download PyAudio wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/

echo [3/4] Setting up config...
if not exist .env copy .env.example .env
mkdir captured_images 2>nul
mkdir models 2>nul

echo [4/4] Instructions:
echo.
echo   1. Install Ollama from: https://ollama.com/download
echo   2. Run: ollama pull gemma2:2b
echo   3. Run: ollama serve
echo   4. In another terminal: python main.py
echo   5. Open: http://localhost:5000
echo.
echo   GPIO is mocked on Windows — all device toggles are simulated.
echo.
pause
