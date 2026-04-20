$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

function Resolve-NodeToolchain {
	$candidates = @(
		'C:\Program Files\nodejs',
		(Join-Path $env:LOCALAPPDATA 'Programs\nodejs')
	)

	foreach ($candidate in $candidates) {
		$nodePath = Join-Path $candidate 'node.exe'
		$npxPath = Join-Path $candidate 'npx.cmd'
		if ((Test-Path -LiteralPath $nodePath) -and (Test-Path -LiteralPath $npxPath)) {
			return [PSCustomObject]@{
				Root = $candidate
				Node = $nodePath
				Npx  = $npxPath
			}
		}
	}

	$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
	$npxCommand = Get-Command npx -ErrorAction SilentlyContinue
	if ($nodeCommand -and $npxCommand) {
		return [PSCustomObject]@{
			Root = Split-Path -Parent $nodeCommand.Source
			Node = $nodeCommand.Source
			Npx  = $npxCommand.Source
		}
	}

	throw 'Node.js toolchain was not found. Install Node.js or add the nodejs directory to PATH.'
}

$nodeToolchain = Resolve-NodeToolchain
if ($env:Path -notlike "*$($nodeToolchain.Root)*") {
	$env:Path = "$($nodeToolchain.Root);$env:Path"
}

& "$scriptRoot\tools\sync-content.ps1"

& $nodeToolchain.Npx --yes antora antora-playbook.yml