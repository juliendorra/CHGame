# Requires Python 3.10+ and arduino-cli on PATH. Uses isolated Arduino data.
param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Work
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
function Run([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit $LASTEXITCODE" }
}
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
if ($hash -ne $ExpectedSha256.ToLowerInvariant()) { throw 'Compiler ZIP checksum mismatch' }
$expanded = Join-Path $Work 'Compiler with spaces'
Expand-Archive -LiteralPath $Archive -DestinationPath $expanded -Force
$prefix = (Get-ChildItem -LiteralPath $expanded -Directory | Where-Object Name -Like 'chgame-gcc-*windows-x86_64').FullName
if (-not $prefix) { throw 'Missing Windows compiler prefix' }
$proof = Join-Path $Work 'validation'
New-Item -ItemType Directory -Force -Path $proof | Out-Null
$env:ARDUINO_DIRECTORIES_DATA = Join-Path $Work 'Arduino data'
$env:ARDUINO_DIRECTORIES_DOWNLOADS = Join-Path $Work 'Arduino downloads'
$env:ARDUINO_DIRECTORIES_USER = Join-Path $Work 'Arduino sketches'
$index = 'https://github.com/bateske/CHGame/releases/download/v0.3.0/package_chgame_index.json'
Run -Program 'python' -Arguments @('--version')
Run -Program 'arduino-cli' -Arguments @('version')
Run -Program 'arduino-cli' -Arguments @('core','update-index','--additional-urls',$index)
Run -Program 'arduino-cli' -Arguments @('core','install','CHGame:ch32v@0.3.0','--additional-urls',$index)
Run -Program 'python' -Arguments @((Join-Path $prefix 'tools/install_release_toolchain.py'),'--toolchain',$prefix,'--arduino-data',$env:ARDUINO_DIRECTORIES_DATA)
Run -Program 'python' -Arguments @((Join-Path $prefix 'tools/verify_current_gcc.py'),'--prefix',$prefix,'--reference-corpus',(Join-Path $prefix 'vendor-corpus.bin'),'--out',(Join-Path $proof 'compiler checks with spaces'),'--exe-suffix','.exe')
Run -Program 'python' -Arguments @((Join-Path $prefix 'tools/test_release_installer.py'))
Run -Program (Join-Path $prefix 'bin/riscv-none-embed-gcc.exe') -Arguments @('--version')
# Exercise ctags without the build-time TMPDIR. Normal Windows TEMP/TMP remain.
$oldTmpdir = $env:TMPDIR
Remove-Item Env:TMPDIR -ErrorAction SilentlyContinue
$fixture = Join-Path $Work 'ctags fixture.cpp'
Set-Content -LiteralPath $fixture -Value "void setup() {}`nvoid loop() {}`n" -Encoding ascii
$tags = & (Join-Path $prefix 'bin/ctags.exe') -u --language-force=c++ -f - --c++-kinds=svpf --fields=KSTtzns --line-directives $fixture
if ($LASTEXITCODE -ne 0 -or -not ($tags -match '^setup\s') -or -not ($tags -match '^loop\s')) { throw 'Arduino ctags prototype test failed' }
if ($null -ne $oldTmpdir) { $env:TMPDIR = $oldTmpdir }
$examples = Join-Path $Repo 'platform/board/arduino/CHGame/libraries/CHGame/examples'
$categories = @((Join-Path $examples 'Games'), (Join-Path $examples 'Apps'))
$sketches = @(Get-ChildItem -LiteralPath $categories -Filter '*.ino' -File -Recurse | Where-Object { $_.Directory.Parent.FullName -in $categories } | Sort-Object FullName)
if ($sketches.Count -ne 23) { throw "Expected 23 upstream examples, found $($sketches.Count)" }
$results = @()
foreach ($sketch in $sketches) {
    Run -Program 'python' -Arguments @((Join-Path $Repo 'tools/chgame.py'),'--sketch',$sketch.Directory.FullName,'build')
    $database = Get-Content -Raw -LiteralPath (Join-Path $sketch.Directory.FullName 'build/release/compile_commands.json') | ConvertFrom-Json
    foreach ($entry in $database) {
        $compiler = [IO.Path]::GetFullPath($entry.arguments[0])
        if (-not $compiler.StartsWith($prefix + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Unexpected Arduino compiler: $compiler" }
    }
    $image = Join-Path $sketch.Directory.FullName ('build/release/' + $sketch.Name + '.bin')
    $results += [pscustomobject]@{sketch=$sketch.BaseName;compiler_commands_verified=$database.Count;image_bytes=(Get-Item -LiteralPath $image).Length;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $image).Hash.ToLowerInvariant()}
    $results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $proof 'firmware.json') -Encoding utf8
}
$probe = Join-Path $prefix 'fixtures/PortProbe'
$libraries = Join-Path $Repo 'platform/board/arduino/CHGame/libraries'
Run -Program 'arduino-cli' -Arguments @('compile','--fqbn','CHGame:ch32v:rev0:opt=oslto,rtlib=nano,periph=game','--build-path',(Join-Path $Work 'PortProbe build with spaces'),'--library',(Join-Path $libraries 'CHGame'),'--library',(Join-Path $libraries 'CHGfx'),'--library',(Join-Path $libraries 'CHSd'),$probe)
Run -Program 'python' -Arguments @((Join-Path $prefix 'tools/install_release_toolchain.py'),'--toolchain',$prefix,'--arduino-data',$env:ARDUINO_DIRECTORIES_DATA,'--restore')
$binaryHashes = @{}
Get-ChildItem -LiteralPath $prefix -File -Recurse | Where-Object { $_.Extension -in @('.exe','.dll') } | ForEach-Object {
    $relative = $_.FullName.Substring($prefix.Length + 1).Replace('\','/')
    $binaryHashes[$relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
}
$report = [pscustomobject]@{passed=$true;binary_sha256=$binaryHashes;environment=[System.Runtime.InteropServices.RuntimeInformation]::OSDescription;processor=$env:PROCESSOR_ARCHITECTURE;archive_sha256=$hash;compiler_checks=$true;installer_checks=$true;ctags_checks=$true;compatibility_alias=$true;upstream_examples=$results.Count;hardware_probe_compile=$true;physical_usb_or_ide_tested=$false}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $proof 'native-windows.json') -Encoding utf8
Write-Output "Native Windows validation passed; reports in $proof"
