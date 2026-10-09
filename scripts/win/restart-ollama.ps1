# Restarts Ollama cleanly and loads the chat model. Stopping "ollama" leaves its llama-server.exe runners alive on
# Windows; they keep their VRAM, and the next model silently spills into shared memory ("100% GPU" in `ollama ps`,
# ~10 tok/s instead of ~60). So the runners are stopped too.
. "$PSScriptRoot\common.ps1"
foreach ($k in 'OLLAMA_KEEP_ALIVE', 'OLLAMA_CONTEXT_LENGTH', 'OLLAMA_MAX_LOADED_MODELS', 'OLLAMA_FLASH_ATTENTION', 'OLLAMA_KV_CACHE_TYPE') {
  $v = [Environment]::GetEnvironmentVariable($k, 'User')
  if ($v) { Set-Item "env:$k" $v }
}
Get-Process "ollama app", "ollama", "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 3
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
if (-not (Wait-Http "http://127.0.0.1:11434/api/version" 30)) { Write-Error "Ollama didn't start"; exit 1 }
$r = Invoke-RestMethod -Method Post http://127.0.0.1:11434/api/generate -ContentType application/json -TimeoutSec 180 `
  -Body (@{ model = $ChatModel; prompt = "Write two sentences about budgets."; stream = $false; keep_alive = -1; options = @{ num_predict = 80 } } | ConvertTo-Json)
Invoke-RestMethod -Method Post http://127.0.0.1:11434/api/embed -ContentType application/json `
  -Body '{"model":"nomic-embed-text","input":"warm","keep_alive":-1}' | Out-Null
"{0}: {1:N0} tok/s (under 25 means VRAM is short: close GPU-heavy apps)" -f $ChatModel, ($r.eval_count / ($r.eval_duration / 1e9))
ollama ps
