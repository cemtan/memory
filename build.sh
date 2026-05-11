#!/bin/bash
pyinstaller \
  --onefile \
  --windowed \
  --clean \
  --name bellek \
  --icon=icon.ico \
  --add-data "bellek.png:." \
  --add-data "icons:icons" \
  --hidden-import PyQt5.QtSvg \
  bellek.py
