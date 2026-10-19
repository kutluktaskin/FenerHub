@echo off
cd /d D:\Projeler\Fenerbahce_Boga\backend
start "Ana API - 8000" cmd /k "D:\Projeler\Fenerbahce_Boga\backend\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
start "Forum API - 8001" cmd /k "D:\Projeler\Fenerbahce_Boga\backend\venv\Scripts\python.exe -m uvicorn forum:app --port 8001"