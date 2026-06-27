@echo off
title Estudio de Voz
cd /d "f:\Projeto IA"
echo Iniciando o Estudio de Voz... (abre no navegador em http://127.0.0.1:5006)
echo (a primeira geracao baixa/carrega o modelo - tenha paciencia)
".venv_omni\Scripts\python.exe" "app\estudio\estudio.py"
pause
