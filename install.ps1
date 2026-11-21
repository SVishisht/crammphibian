# Crammphibian installer for Windows.
# Usage (in PowerShell, inside this folder):
#   powershell -ExecutionPolicy Bypass -File install.ps1          standard models (~2.3 GB)
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Lite    smallest models (~450 MB, <1 GB RAM)
param([switch]$Lite)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Lite) { $DefEmbed = "all-minilm"; $DefLlm = "qwen2.5:0.5b"; $Size = "~450 MB" }
else       { $DefEmbed = "nomic-embed-text"; $DefLlm = "llama3.2:3b"; $Size = "~2.3 GB" }
$EmbedModel = if ($env:CRAMMPHIBIAN_EMBED_MODEL) { $env:CRAMMPHIBIAN_EMBED_MODEL } else { $DefEmbed }
$LlmModel   = if ($env:CRAMMPHIBIAN_LLM_MODEL)   { $env:CRAMMPHIBIAN_LLM_MODEL }   else { $DefLlm }

$py = $null
foreach ($c in @("py -3", "python")) {
    try {
        $parts = $c.Split(" ")
        & $parts[0] $parts[1..9] -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $parts; break }
    } catch {}
}
if (-not $py) {
    Write-Host "Python 3.10+ is required. Install it from https://www.python.org/downloads/ (tick 'Add to PATH'), then run this again." -ForegroundColor Red
    exit 1
}

Write-Host "-> Creating a private Python environment in .venv"
& $py[0] $py[1..9] -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
Write-Host "-> Installing Crammphibian (a minute or two the first time)"
& .\.venv\Scripts\python.exe -m pip install --quiet -e .

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "-> Downloading local AI models with Ollama (one time, $Size)"
    ollama pull $EmbedModel
    ollama pull $LlmModel
} else {
    Write-Host ""
    Write-Host "Ollama isn't installed. It runs the AI models on your computer." -ForegroundColor Yellow
    Write-Host "  1. Install it from https://ollama.com/download"
    Write-Host "  2. Then run:  ollama pull $EmbedModel ; ollama pull $LlmModel"
}

Set-Content -Path start.bat -Value "@echo off`r`nif not defined CRAMMPHIBIAN_EMBED_MODEL set CRAMMPHIBIAN_EMBED_MODEL=$EmbedModel`r`nif not defined CRAMMPHIBIAN_LLM_MODEL set CRAMMPHIBIAN_LLM_MODEL=$LlmModel`r`ncd /d %~dp0`r`n.venv\Scripts\crammphibian.exe %*"
Write-Host ""
Write-Host "Done. Start it any time by double-clicking start.bat" -ForegroundColor Green
