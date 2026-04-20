$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$antoraRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $antoraRoot
$componentRoot = Join-Path $antoraRoot 'reference-model'
$pagesRoot = Join-Path $componentRoot 'modules\ROOT\pages'
$navPath = Join-Path $componentRoot 'modules\ROOT\nav.adoc'

function Remove-PathIfExists {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Sync-Junction {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )

    Remove-PathIfExists -Path $LinkPath
    if (Test-Path -LiteralPath $TargetPath) {
        New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null
    }
}

function Sync-DirectoryCopies {
    param(
        [string]$SourcePath,
        [string]$TargetPath
    )

    Remove-PathIfExists -Path $TargetPath
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        return
    }

    New-Item -ItemType Directory -Path $TargetPath | Out-Null
    Get-ChildItem -LiteralPath $SourcePath -File -Filter *.adoc | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $TargetPath $_.Name)
    }
}

function Sync-DomainPublicationTree {
    param(
        [string]$SourceDomainPath,
        [string]$TargetDomainPath
    )

    Remove-PathIfExists -Path $TargetDomainPath
    New-Item -ItemType Directory -Path $TargetDomainPath | Out-Null

    foreach ($entry in Get-ChildItem -LiteralPath $SourceDomainPath) {
        if (-not $entry.PSIsContainer) {
            continue
        }

        switch ($entry.Name) {
            '.summary' {
                Sync-DirectoryCopies -SourcePath $entry.FullName -TargetPath (Join-Path $TargetDomainPath 'summary')
            }
            'domains' {
                $childDomainsTarget = Join-Path $TargetDomainPath 'domains'
                Remove-PathIfExists -Path $childDomainsTarget
                New-Item -ItemType Directory -Path $childDomainsTarget | Out-Null
                foreach ($childDomain in Get-ChildItem -LiteralPath $entry.FullName -Directory | Sort-Object Name) {
                    Sync-DomainPublicationTree -SourceDomainPath $childDomain.FullName -TargetDomainPath (Join-Path $childDomainsTarget $childDomain.Name)
                }
            }
            default {
                Sync-Junction -LinkPath (Join-Path $TargetDomainPath $entry.Name) -TargetPath $entry.FullName
            }
        }
    }
}

function Get-DocTitle {
    param([string]$FilePath)

    $match = Select-String -Path $FilePath -Pattern '^=\s+(.+)$' | Select-Object -First 1
    if ($match) {
        return $match.Matches[0].Groups[1].Value.Trim()
    }

    return [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
}

function Add-NavLine {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [int]$Level,
        [string]$Text
    )

    $prefix = ''.PadLeft($Level, '*')
    $Lines.Add("$prefix $Text")
}

function Get-RelativePagePath {
    param([string]$FilePath)

    return $FilePath.Substring($pagesRoot.Length + 1).Replace('\', '/')
}

function Get-AdocFiles {
    param([string[]]$Paths)

    $files = foreach ($path in $Paths) {
        if (Test-Path -LiteralPath $path) {
            Get-ChildItem -LiteralPath $path -Recurse -File -Filter *.adoc
        }
    }

    return @($files | Sort-Object FullName)
}

function New-TextFromCodePoints {
    param([int[]]$CodePoints)

    return (-join ($CodePoints | ForEach-Object { [char]$_ }))
}

function Add-FileEntries {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [int]$Level,
        [System.IO.FileInfo[]]$Files
    )

    foreach ($file in $Files) {
        $relative = Get-RelativePagePath -FilePath $file.FullName
        $title = Get-DocTitle -FilePath $file.FullName
        Add-NavLine -Lines $Lines -Level $Level -Text "xref:$relative[$title]"
    }
}

$captionValueContext = New-TextFromCodePoints -CodePoints @(0x0426, 0x0435, 0x043D, 0x043D, 0x043E, 0x0441, 0x0442, 0x044C, 0x0020, 0x0438, 0x0020, 0x043A, 0x043E, 0x043D, 0x0442, 0x0435, 0x043A, 0x0441, 0x0442)
$captionProductBehavior = New-TextFromCodePoints -CodePoints @(0x041F, 0x043E, 0x0432, 0x0435, 0x0434, 0x0435, 0x043D, 0x0438, 0x0435, 0x0020, 0x043F, 0x0440, 0x043E, 0x0434, 0x0443, 0x043A, 0x0442, 0x0430)
$captionConstraintsControl = New-TextFromCodePoints -CodePoints @(0x041E, 0x0433, 0x0440, 0x0430, 0x043D, 0x0438, 0x0447, 0x0435, 0x043D, 0x0438, 0x044F, 0x0020, 0x0438, 0x0020, 0x043A, 0x043E, 0x043D, 0x0442, 0x0440, 0x043E, 0x043B, 0x044C)
$captionTechnicalInfo = New-TextFromCodePoints -CodePoints @(0x0422, 0x0435, 0x0445, 0x043D, 0x0438, 0x0447, 0x0435, 0x0441, 0x043A, 0x0430, 0x044F, 0x0020, 0x0438, 0x043D, 0x0444, 0x043E, 0x0440, 0x043C, 0x0430, 0x0446, 0x0438, 0x044F)
$captionSubdomains = New-TextFromCodePoints -CodePoints @(0x041F, 0x043E, 0x0434, 0x0434, 0x043E, 0x043C, 0x0435, 0x043D, 0x044B)

$publicationBlocks = @(
    @{
        Caption = 'Summary'
        LayerDirs = @('summary')
    },
    @{
        Caption = $captionValueContext
        LayerDirs = @(
            '01-layer-aeilus-value-streams',
            '02-layer-context-boundaries',
            '03-layer-stakeholders-motivation',
            '04-layer-strategy-product',
            '05-layer-business-architecture'
        )
    },
    @{
        Caption = $captionProductBehavior
        LayerDirs = @(
            '06-layer-processes',
            '07-layer-scenarios-ux',
            '09-layer-domain-rules',
            '33-layer-critical-path'
        )
    },
    @{
        Caption = $captionConstraintsControl
        LayerDirs = @(
            '08-layer-requirements',
            '17-layer-nfr-quality-attributes',
            '18-layer-risks',
            '29-layer-compliance',
            '30-layer-security',
            '31-layer-access-rights',
            '32-layer-performance'
        )
    },
    @{
        Caption = 'Change'
        LayerDirs = @(
            '19-layer-technical-debt',
            '22-layer-changes-roadmap',
            '23-layer-development-tasks',
            '26-layer-business-hypotheses',
            '27-layer-economics-validation',
            '28-layer-engineering-process-capability'
        )
    },
    @{
        Caption = $captionTechnicalInfo
        LayerDirs = @(
            '10-layer-applications-architecture',
            '11-layer-api-interfaces',
            '12-layer-integrations',
            '13-layer-data-architecture',
            '14-layer-code-implementation',
            '15-layer-technology-architecture',
            '16-layer-operations',
            '20-layer-quality-testing',
            '21-layer-observability',
            '24-layer-knowledge-sources',
            '25-layer-traceability'
        )
    }
)

function Add-SectionNav {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [string]$SectionName,
        [string]$Caption
    )

    $sectionPath = Join-Path $pagesRoot $SectionName
    if (-not (Test-Path -LiteralPath $sectionPath)) {
        return
    }

    Add-NavLine -Lines $Lines -Level 1 -Text $Caption
    $files = Get-ChildItem -LiteralPath $sectionPath -Recurse -File -Filter *.adoc |
        Where-Object { $_.FullName -notmatch '[\\/]\.summary([\\/]|$)' } |
        Sort-Object FullName
    foreach ($file in $files) {
        $relative = Get-RelativePagePath -FilePath $file.FullName
        $title = Get-DocTitle -FilePath $file.FullName
        Add-NavLine -Lines $Lines -Level 2 -Text "xref:$relative[$title]"
    }
}

function Add-DomainBlockNav {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [int]$Level,
        [string]$DomainPath,
        [hashtable]$Block
    )

    $paths = foreach ($layerDir in $Block.LayerDirs) {
        Join-Path $DomainPath $layerDir
    }
    $files = Get-AdocFiles -Paths $paths
    if ($files.Count -eq 0) {
        return
    }

    Add-NavLine -Lines $Lines -Level $Level -Text $Block.Caption
    Add-FileEntries -Lines $Lines -Level ($Level + 1) -Files $files
}

function Add-DomainNav {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [int]$Level,
        [string]$DomainPath
    )

    if (-not (Test-Path -LiteralPath $DomainPath)) {
        return
    }

    $domainName = Split-Path -Leaf $DomainPath
    Add-NavLine -Lines $Lines -Level $Level -Text $domainName

    foreach ($block in $publicationBlocks) {
        Add-DomainBlockNav -Lines $Lines -Level ($Level + 1) -DomainPath $DomainPath -Block $block
    }

    $childContainer = Join-Path $DomainPath 'domains'
    if (-not (Test-Path -LiteralPath $childContainer)) {
        return
    }

    $childDomains = @(Get-ChildItem -LiteralPath $childContainer -Directory | Sort-Object Name)
    if ($childDomains.Count -eq 0) {
        return
    }

    Add-NavLine -Lines $Lines -Level ($Level + 1) -Text $captionSubdomains
    foreach ($childDomain in $childDomains) {
        Add-DomainNav -Lines $Lines -Level ($Level + 2) -DomainPath $childDomain.FullName
    }
}

function Add-DomainsNav {
    param([System.Collections.Generic.List[string]]$Lines)

    $domainsPath = Join-Path $pagesRoot 'domains'
    if (-not (Test-Path -LiteralPath $domainsPath)) {
        return
    }

    $topDomains = @(Get-ChildItem -LiteralPath $domainsPath -Directory | Sort-Object Name)
    if ($topDomains.Count -eq 0) {
        return
    }

    Add-NavLine -Lines $Lines -Level 1 -Text 'domains'
    foreach ($topDomain in $topDomains) {
        Add-DomainNav -Lines $Lines -Level 2 -DomainPath $topDomain.FullName
    }
}

Sync-Junction -LinkPath (Join-Path $pagesRoot '00-meta') -TargetPath (Join-Path $repoRoot '00-meta')
Sync-Junction -LinkPath (Join-Path $pagesRoot 'common') -TargetPath (Join-Path $repoRoot 'common')

$domainsSourcePath = Join-Path $repoRoot 'domains'
$domainsPublicationPath = Join-Path $pagesRoot 'domains'
Remove-PathIfExists -Path $domainsPublicationPath
if (Test-Path -LiteralPath $domainsSourcePath) {
    New-Item -ItemType Directory -Path $domainsPublicationPath | Out-Null
    foreach ($topDomain in Get-ChildItem -LiteralPath $domainsSourcePath -Directory | Sort-Object Name) {
        Sync-DomainPublicationTree -SourceDomainPath $topDomain.FullName -TargetDomainPath (Join-Path $domainsPublicationPath $topDomain.Name)
    }
}

$navLines = [System.Collections.Generic.List[string]]::new()
$navLines.Add('* xref:index.adoc[VSS Editor Product Model]')
Add-SectionNav -Lines $navLines -SectionName '00-meta' -Caption '00-meta'
Add-SectionNav -Lines $navLines -SectionName 'common' -Caption 'common'
Add-DomainsNav -Lines $navLines

[System.IO.File]::WriteAllLines($navPath, $navLines, [System.Text.UTF8Encoding]::new($false))
Write-Output 'Antora content junctions and navigation synchronized.'