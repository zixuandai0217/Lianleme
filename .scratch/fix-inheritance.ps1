$log = 'R:\Lianleme\.scratch\acl-fix.log'
"start $(Get-Date -Format o)" | Out-File -FilePath $log -Encoding utf8
foreach ($p in @('R:\Lianleme\backend', 'R:\Lianleme\web', 'R:\Lianleme\docs', 'R:\Lianleme\.git', 'R:\Lianleme\infra')) {
    $out = & icacls $p /inheritance:e 2>&1
    "--- $p exit=$LASTEXITCODE" | Out-File -FilePath $log -Append -Encoding utf8
    $out | Out-File -FilePath $log -Append -Encoding utf8
}
"done" | Out-File -FilePath $log -Append -Encoding utf8
