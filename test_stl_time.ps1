Write-Host "Starting STL parser test..."

$filename = "Dji+Avata+2+Simple.stl"
Write-Host "Testing file: $filename"

# 检查文件是否存在
if (-not (Test-Path $filename)) {
    Write-Host "File does not exist" -ForegroundColor Red
    exit 1
}
Write-Host "File exists"

# 开始计时
$start = Get-Date
Write-Host "Starting parsing..."

# 读取文件
$bytes = [System.IO.File]::ReadAllBytes($filename)

# 跳过文件头（80字节）
$triangleCountBytes = $bytes[80..83]
$triangleCount = [System.BitConverter]::ToUInt32($triangleCountBytes, 0)
Write-Host "Triangle count: $triangleCount"

# 计算解析时间
$end = Get-Date
$duration = ($end - $start).TotalMilliseconds

Write-Host "Successfully read $triangleCount triangles"
Write-Host "Parsing time: $duration ms"

Write-Host "Test completed."