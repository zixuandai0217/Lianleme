param([string]$Log = 'R:\Lianleme\.scratch\run.log', [string]$WorkDir = 'R:\Lianleme')
Set-Location $WorkDir
"=== started $(Get-Date -Format o) ===" | Out-File -FilePath $Log -Encoding utf8
& uv run --directory R:\Lianleme\backend pytest -q *>> $Log
"=== exit=$LASTEXITCODE ===" | Out-File -FilePath $Log -Append -Encoding utf8
