@echo off
echo Installing Stock Dashboard Dependencies...
echo.

echo Step 1: Installing Python packages...
pip install -r requirements.txt

echo.
echo Step 2: Verifying installation...
python -c "import pandas; print('Pandas installed successfully')"
python -c "import dash; print('Dash installed successfully')"
python -c "import yfinance; print('yfinance installed successfully')"
python -c "import numpy; print('NumPy installed successfully')"

echo.
echo Step 3: Testing critical imports...
python -c "import sys; sys.path.append('.'); import data_manager; print('data_manager imports successfully')"

echo.
echo Installation complete! You can now run the dashboard with:
echo python app.py
echo.
pause