@echo off
REM Signal Mesh — daily launcher
REM Called by Windows Task Scheduler every weekday at 09:00 AM.
REM TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as user environment variables.

cd /d "C:\Users\mailt\Desktop\claude_code_course\signal_mesh"

"C:\Users\mailt\Desktop\claude_code_course\signal_mesh\.venv\Scripts\python.exe" ^
    "C:\Users\mailt\Desktop\claude_code_course\signal_mesh\int\bin\signal_mesh_orchestrator.py" ^
    fetch_data -v -e --agent all --bulk_prompt --output
