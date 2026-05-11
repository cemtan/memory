#!/bin/bash
python3 -m venv build-env
source build-env/bin/activate
pip install --upgrade pip
pip install PyQt5 pyinstaller

pyinstaller \
  --onefile \
  --windowed \
  --clean \
  --name bellek \
  --icon=icon.ico \
  --add-data "icons/bellek.png:." \
  --add-data "icons:icons" \
  --hidden-import PyQt5.QtSvg \
  bellek.py
