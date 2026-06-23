$Port = if ($args.Count -gt 0) { [int]$args[0] } else { 8765 }
Set-Location $PSScriptRoot
python main.py serve --host 127.0.0.1 --port $Port
