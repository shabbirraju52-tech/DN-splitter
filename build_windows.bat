@echo off
setlocal
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name DeliveryNoteSplitter dn_splitter.py
pause
