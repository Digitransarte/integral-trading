@echo off
REM ============================================================
REM  Integral Trading — Configuração do Task Scheduler
REM  Corre este ficheiro UMA VEZ como Administrador
REM  Clique direito > "Executar como administrador"
REM ============================================================

echo.
echo  Integral Trading — A configurar tarefas agendadas...
echo.

REM Caminho para o Python do venv e scripts
set PYTHON=C:\integral-trading\venv\Scripts\python.exe
set SCRIPTS=C:\integral-trading

REM ── Tarefa 1: Scanner EP diário (14:00 UTC = 9:00 ET / 15:00 Portugal hora de verao) ──
schtasks /create /tn "IntegralTrading_Scanner" ^
  /tr "%PYTHON% %SCRIPTS%\scheduled_scan.py" ^
  /sc WEEKLY ^
  /d MON,TUE,WED,THU,FRI ^
  /st 15:00 ^
  /ru "%USERNAME%" ^
  /rl HIGHEST ^
  /f ^
  /it

if %errorlevel% == 0 (
    echo  [OK] Scanner EP agendado para as 15:00 Segunda a Sexta
) else (
    echo  [ERRO] Falha ao criar tarefa Scanner
)

REM ── Tarefa 2: Actualização do Tracker (21:30 UTC = 16:30 ET / 22:30 Portugal hora de verao) ──
schtasks /create /tn "IntegralTrading_Tracker" ^
  /tr "%PYTHON% %SCRIPTS%\scheduled_update.py" ^
  /sc WEEKLY ^
  /d MON,TUE,WED,THU,FRI ^
  /st 22:30 ^
  /ru "%USERNAME%" ^
  /rl HIGHEST ^
  /f ^
  /it

if %errorlevel% == 0 (
    echo  [OK] Tracker agendado para as 22:30 Segunda a Sexta
) else (
    echo  [ERRO] Falha ao criar tarefa Tracker
)

REM ── Configurar "Run as soon as possible after missed start" ──
schtasks /change /tn "IntegralTrading_Scanner" /ri 1
schtasks /change /tn "IntegralTrading_Tracker" /ri 1

echo.
echo  Tarefas criadas. Para verificar:
echo  schtasks /query /tn "IntegralTrading_Scanner"
echo  schtasks /query /tn "IntegralTrading_Tracker"
echo.
echo  Para correr manualmente agora:
echo  schtasks /run /tn "IntegralTrading_Scanner"
echo  schtasks /run /tn "IntegralTrading_Tracker"
echo.
pause
