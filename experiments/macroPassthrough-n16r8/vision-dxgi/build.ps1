$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
cmake -S $here -B (Join-Path $here 'build') -G 'Visual Studio 17 2022' -A x64
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cmake --build (Join-Path $here 'build') --config Release
exit $LASTEXITCODE
