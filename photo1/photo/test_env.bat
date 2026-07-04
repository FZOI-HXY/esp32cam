@echo off
echo Testing Python environment...
python --version
echo.
echo Testing pip...
python -m pip --version
echo.
echo Testing Flask installation...
python -c "import flask; print('Flask version:', flask.__version__)"
pause
