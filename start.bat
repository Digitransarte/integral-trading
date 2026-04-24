@echo off
cd /d C:\integral-trading
call venv\Scripts\activate
echo.
echo  ◈ Integral Trading
echo  Dashboard a iniciar em http://localhost:8501
echo  Prima Ctrl+C para parar
echo.
streamlit run dashboard/app.py
