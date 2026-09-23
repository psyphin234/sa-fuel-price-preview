Set-Location "$PSScriptRoot\backend"
python -m pip install --quiet -r requirements.txt
Write-Host "Starting SA Basic Fuel Price Preview at http://127.0.0.1:5057 ..."
Start-Process "http://127.0.0.1:5057"
python app.py
