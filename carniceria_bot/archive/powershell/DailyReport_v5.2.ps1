<#

===========================================================

  DailyReport_v5.2.ps1 (Stability + WhatIf/ValidateOnly + Performance)

  - Reads 2 Outlook emails (Open / Closed), extracts CSV/XLSX attachments

  - Normalizes columns, states, dates, and analyst names

  - Maps analysts to teams (token match + fuzzy + cache)

  - Computes KPIs (Backlog = business days)

  - Generates daily dashboard HTML (OneDrive + Desktop)

  - Sends Outlook email with full-width template + TL;DR + progress bar

  - Logging + end-of-run summary

 

Key v5.2 improvements:

  - Enforced STA for Outlook/Excel COM automation

  - Real ShouldProcess usage; -WhatIf becomes plan-only (no disk writes / no email)

  - ValidateOnly becomes non-destructive (no attachment saving, no outputs, no email)

  - Faster business-day age calculation (no day-by-day loop)

  - Stronger column-name normalization (underscores/dots/dashes tolerated)

  - Reduced COM double-release risk

  - Optional dedup by ticket number (default ON)

 

Compatibility:

  - Windows PowerShell 5.1 (recommended) or PowerShell 7+ (Windows only)

  - Requires local Outlook installed/configured

  - Excel required ONLY when attachments are .xlsx (COM)

 

===========================================================

#>

 

[CmdletBinding(SupportsShouldProcess = $true)]

param(

    [string]$RootFolder = "poner path",

    [string]$TeamsCsv = "poner path",

 

    [int]$BacklogAgeDays = 3,

    [int]$MailLookbackDays = 14, # kept for compatibility but TODAY-only is enforced in Outlook search

 

    [string]$OpenSubjectKeyword = "Daily Report - Open",

    [string]$ClosedSubjectKeyword = "Daily Report - Closed",

 

    [string]$AgingLink = "poner link",
 

    [string[]]$To = @('poner mail'),

    [string[]]$Cc = @(),

 

    # Optional: force which Outlook account is used to send

    [string]$FromSmtpAddress = "",

 

    # Local OneDrive sync root where dashboards are written

    [string]$DashboardLocalRoot = "poner path",

 

    # SharePoint base URL used to build the month folder link in the email

    [string]$DashboardSharePointBaseUrl = "poner link",

 

    # Optional: override log file path (otherwise auto-generated under RootFolder\logs)

    [string]$LogFilePath = "",

 

    # Operational switches

    [switch]$SkipDashboard,

    [switch]$SkipEmail,

    [switch]$ValidateOnly,

 

    # v5.2: default ON dedup by ticket number; set to disable if you want raw counts

    [switch]$DisableDedup,

 

    # Opens the log file at the end (interactive runs)

    [switch]$OpenLog

)

 

Set-StrictMode -Version Latest

 

# -------------------------

# Script-scoped state

# -------------------------

$Script:Version = "5.2"

$Script:RunId = [guid]::NewGuid().ToString()

$Script:StartTs = Get-Date

 

$Script:LogsRoot = Join-Path $RootFolder "logs"

$Script:OutRoot = Join-Path $RootFolder "Output"

 

if ([string]::IsNullOrWhiteSpace($LogFilePath)) {

    $Script:LogFile = Join-Path $Script:LogsRoot ("DailyReport_v5_2_" + (Get-Date -f "yyyyMMdd_HHmmss") + "_$($Script:RunId).log")

}
else {

    $Script:LogFile = $LogFilePath

}

 

# -------------------------

# Logging

# -------------------------

function Write-Log {

    param(

        [ValidateSet('INFO', 'WARN', 'ERROR', 'DEBUG')]

        [string]$Level = 'INFO',

        [string]$Source = "DailyReport_v$($Script:Version)",

        [Parameter(Mandatory = $true)]

        [string]$Message

    )

 

    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")

    $line = "$ts | $Level | $Source | $Message"

    Write-Host $line

    if (-not [string]::IsNullOrWhiteSpace($Script:LogFile)) {

        Add-Content -Path $Script:LogFile -Value $line -Encoding UTF8

    }

}

 

function New-LogFile {

    if (-not (Test-Path $Script:LogsRoot)) {

        New-Item -ItemType Directory -Path $Script:LogsRoot -Force | Out-Null

    }

    New-Item -ItemType File -Path $Script:LogFile -Force | Out-Null

}

 

function Assert-Valid {

    param(

        [Parameter(Mandatory = $true)][bool]$Condition,

        [Parameter(Mandatory = $true)][string]$ErrorMessage

    )

    if (-not $Condition) {

        Write-Log -Level ERROR -Source 'Assert' -Message $ErrorMessage

        throw $ErrorMessage

    }

}

 

function Get-RowCount {

    param($Obj)

    if ($null -eq $Obj) { return 0 }

    try { return ($Obj | Measure-Object).Count } catch { return 0 }

}

 

function Release-ComObjectSafeOnce {

    param([Parameter(Mandatory = $true)][ref]$ComObjectRef)

    if ($null -eq $ComObjectRef.Value) { return }

    try { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ComObjectRef.Value) } catch { }

    finally { $ComObjectRef.Value = $null }

}

 

function Invoke-GC {

    [gc]::Collect()

    [gc]::WaitForPendingFinalizers()

    [gc]::Collect()

}

 

function New-SafeFileName {

    param([Parameter(Mandatory = $true)][string]$Name)

    $invalid = [IO.Path]::GetInvalidFileNameChars()

    $sb = New-Object System.Text.StringBuilder

    foreach ($ch in $Name.ToCharArray()) {

        if ($invalid -contains $ch) { [void]$sb.Append('_') } else { [void]$sb.Append($ch) }

    }

    return $sb.ToString()

}

 

function To-TrimmedString {

    param($Value)

    if ($null -eq $Value) { return "" }

    $s = $Value.ToString()

    if ($null -eq $s) { return "" }

    return $s.Trim()

}

 

# -------------------------

# ShouldProcess wrapper

# -------------------------

function Invoke-Change {

    [CmdletBinding(SupportsShouldProcess = $true)]

    param(

        [Parameter(Mandatory = $true)][string]$Target,

        [Parameter(Mandatory = $true)][string]$Action,

        [Parameter(Mandatory = $true)][scriptblock]$ScriptBlock

    )

 

    if ($ValidateOnly.IsPresent) {

        Write-Log -Source 'ValidateOnly' -Message ("ValidateOnly: would {0}: {1}" -f $Action, $Target)

        return $false

    }

 

    if ($PSCmdlet.ShouldProcess($Target, $Action)) {

        & $ScriptBlock

        return $true

    }
    else {

        Write-Log -Source 'WhatIf' -Message ("WhatIf: would {0}: {1}" -f $Action, $Target)

        return $false

    }

}

 

# -------------------------

# Preflight: STA / environment

# -------------------------

function Assert-ComApartmentState {

    $state = [System.Threading.Thread]::CurrentThread.ApartmentState

    if ($state -ne [System.Threading.ApartmentState]::STA) {

        $msg = "This script uses Outlook/Excel COM automation. Current thread is '$state'. Run PowerShell with -STA."

        if ($PSVersionTable.PSVersion.Major -ge 7) {

            throw ($msg + " Example: pwsh.exe -STA -File .\DailyReport_v5.2.ps1")

        }
        else {

            # Windows PowerShell can sometimes still work, but COM is less reliable in MTA.

            throw ($msg + " Example: powershell.exe -STA -File .\DailyReport_v5.2.ps1")

        }

    }

}

 

function Import-CsvUtf8 {

    param([Parameter(Mandatory = $true)][string]$Path)

    return Import-Csv -Path $Path -Encoding UTF8

}

 

function Initialize-Environment {

    if (-not (Test-Path $RootFolder)) { New-Item -ItemType Directory -Path $RootFolder -Force | Out-Null }

    if (-not (Test-Path $Script:OutRoot)) { New-Item -ItemType Directory -Path $Script:OutRoot -Force | Out-Null }

 

    New-LogFile

    Write-Log -Message ("Version={0} | RunId={1} | StartTime={2} | ValidateOnly={3} | WhatIf={4}" -f `

        $Script:Version, $Script:RunId, $Script:StartTs, $ValidateOnly.IsPresent, $WhatIfPreference)

 

    Assert-Valid -Condition (Test-Path $TeamsCsv) -ErrorMessage ("Teams CSV not found: {0}" -f $TeamsCsv)

    Assert-Valid -Condition (($To | Measure-Object).Count -gt 0) -ErrorMessage "Recipient list 'To' is empty."

 

    # Validate Teams.csv schema

    $sample = Import-CsvUtf8 -Path $TeamsCsv | Select-Object -First 1

    Assert-Valid -Condition ($null -ne $sample) -ErrorMessage ("Teams CSV is empty: {0}" -f $TeamsCsv)

    Assert-Valid -Condition ($sample.PSObject.Properties.Name -contains 'assigned_to') -ErrorMessage "Teams CSV must contain column: assigned_to"

    Assert-Valid -Condition ($sample.PSObject.Properties.Name -contains 'team')        -ErrorMessage "Teams CSV must contain column: team"

 

    # COM apartment state (fail fast)

    Assert-ComApartmentState

    Write-Log -Message "STA check: OK"

 

    # Outlook COM availability

    $tmpOutlook = $null

    try {

        $tmpOutlook = New-Object -ComObject Outlook.Application

        Write-Log -Message "Outlook COM check: OK"

    }
    catch {

        throw ("Outlook COM check failed. Ensure Outlook is installed and configured. Error: {0}" -f $($_.Exception.Message))

    }
    finally {

        if ($tmpOutlook) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$tmpOutlook) }

        Invoke-GC

    }

}

 

# -------------------------

# Text normalization

# -------------------------

function Normalize-Text {

    param([string]$Text)

 

    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }

 

    $t = $Text.Trim()

 

    # Remove invisible Unicode chars that break equality

    $t = $t.Replace([char]0x00A0, ' ')              # NBSP

    $t = $t -replace "[\u200B-\u200D\uFEFF]", ""    # zero-width + BOM

 

    $t = $t.ToLowerInvariant()

 

    # Strip diacritics (FormD)

    $formD = $t.Normalize([Text.NormalizationForm]::FormD)

    $sb = New-Object -TypeName System.Text.StringBuilder

    foreach ($ch in $formD.ToCharArray()) {

        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch) -ne 'NonSpacingMark') {

            [void]$sb.Append($ch)

        }

    }

    $t = $sb.ToString()

 

    # Keep letters/digits/space; replace the rest with space

    $t = $t -replace '[^\p{L}\p{Nd}\s]', ' '

    $t = $t -replace '\s+', ' '

 

    return $t.Trim()

}

 

function Normalize-AnalystKey {

    param([string]$Name)

 

    if ([string]::IsNullOrWhiteSpace($Name)) { return "" }

 

    $n = $Name.Trim()

 

    # "Last, First" -> "First Last"

    if ($n -match ',') {

        $parts = $n -split ',', 2

        if ($parts.Count -eq 2) {

            $n = ($parts[1].Trim() + " " + $parts[0].Trim())

        }

    }

 

    # Remove emails if present

    $n = $n -replace '\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b', ' '

 

    # Remove parentheses content

    $n = $n -replace '\([^)]*\)', ' '

 

    # Important: remove apostrophes without inserting space (helps "O'Connor" -> "oconnor")

    $n = $n -replace "[’']", ""

 

    $n = Normalize-Text $n

 

    $noise = @('external', 'contractor', 'vendor', 'temp', 'temporary', 'intern', 'pwc')

    $tokens = New-Object System.Collections.Generic.List[string]

    foreach ($tok in ($n -split ' ')) {

        if ([string]::IsNullOrWhiteSpace($tok)) { continue }

        if ($noise -contains $tok) { continue }

        $tokens.Add($tok) | Out-Null

    }

 

    return (($tokens -join ' ').Trim())

}

 

function Get-NameTokens {

    param([string]$NormalizedName)

    if ([string]::IsNullOrWhiteSpace($NormalizedName)) { return @() }

    return @($NormalizedName.Split(' ') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

}

 

# -------------------------

# Column helpers (v5.2: stronger normalization)

# -------------------------

function Normalize-ColName {

    param([string]$Name)

    if ([string]::IsNullOrWhiteSpace($Name)) { return "" }

 

    # Remove all non-alphanumeric (handles spaces, underscores, dots, dashes)

    return (($Name.ToLowerInvariant()) -replace '[^a-z0-9]', '')

}

 

function Find-ColumnName {

    param(

        [Parameter(Mandatory = $true)]$SampleRow,

        [Parameter(Mandatory = $true)][string[]]$Candidates

    )

 

    $props = $SampleRow.PSObject.Properties

    $normMap = @{}

    foreach ($p in $props) { $normMap[(Normalize-ColName $p.Name)] = $p.Name }

 

    $aliases = @{

        'number'      = @('number', 'ticket', 'id', 'task', 'incident', 'reference', 'ref', 'req', 'request', 'ritm', 'sctask', 'inc')

        'assigned to' = @('assignedto', 'assignto', 'assignee', 'owner', 'closedby', 'resolvedby', 'analyst', 'agent', 'assignedto.name', 'assigned_to')

        'opened'      = @('opened', 'openedat', 'created', 'createdon', 'start', 'submittedon', 'reportedon', 'reportedat', 'opened_at', 'sys_created_on')

        'state'       = @('state', 'status', 'currentstate', 'ticketstate', 'requeststate', 'stage', 'phase', 'progress', 'resolutionstate', 'closecode', 'closurestatus')

    }

 

    foreach ($cand in $Candidates) {

        $candKey = $cand.ToLowerInvariant()

        $candNorm = Normalize-ColName $cand

 

        if ($normMap.ContainsKey($candNorm)) { return $normMap[$candNorm] }

 

        if ($aliases.ContainsKey($candKey)) {

            foreach ($alt in $aliases[$candKey]) {

                $altNorm = Normalize-ColName $alt

                if ($normMap.ContainsKey($altNorm)) { return $normMap[$altNorm] }

            }

        }

 

        $firstWord = ($cand.Split()[0])

        $hit = $props | Where-Object { $($_.Name) -match ("^(?i)\s*" + [Regex]::Escape($firstWord)) } | Select-Object -First 1

        if ($hit) { return $hit.Name }

    }

 

    return $null

}

 

# -------------------------

# Dates (v5.2: reduce culture ambiguity)

# -------------------------

function Parse-DateSafe {

    param($Value)

 

    if ($null -eq $Value) { return $null }

    if ($Value -is [datetime]) { return [datetime]$Value }

 

    # Excel serial

    if ($Value -is [double] -or $Value -is [int]) {

        try { return (Get-Date "1899-12-30").AddDays([double]$Value) } catch { return $null }

    }

 

    $s = (To-TrimmedString $Value)

    if ([string]::IsNullOrWhiteSpace($s)) { return $null }

 

    if ($s -match '^[0-9]+(\.[0-9]+)?$') {

        try { return (Get-Date "1899-12-30").AddDays([double]$s) } catch { }

    }

 

    foreach ($f in @(

            "yyyy-MM-ddTHH:mm:ss",

            "yyyy-MM-dd HH:mm:ss",

            "yyyy-MM-dd",

            "MM/dd/yyyy HH:mm",

            "MM/dd/yyyy",

            "dd/MM/yyyy HH:mm",

            "dd/MM/yyyy"

        )) {

        try { return [datetime]::ParseExact($s, $f, [System.Globalization.CultureInfo]::InvariantCulture) } catch { }

    }

 

    # Last resort: allow OS culture parsing

    try { return [datetime]::Parse($s) } catch { }

 

    return $null

}

 

# -------------------------

# State normalization

# -------------------------

function Normalize-State {

    param([string]$StateRaw)

    if ([string]::IsNullOrWhiteSpace($StateRaw)) { return 'Open' }

 

    $s = ($StateRaw -replace '[^a-zA-Z\s]', ' ') -replace '\s+', ' '

    $s = $s.Trim().ToLowerInvariant()

 

    if ($s -match 'close|closed|closure|complete|completed|resolve|resolved|done|finished|terminated|fulfilled|implemented') { return 'Closed' }

    if ($s -match 'pending|await|hold|on hold|waiting|pause|suspend|deferred|temporarily') { return 'Pending' }

    return 'Open'

}

 

# -------------------------

# Outlook intake

# -------------------------

function Get-OutlookFolderPath {

    param([Parameter(Mandatory = $true)]$Folder)

 

    $names = New-Object System.Collections.Generic.List[string]

    $cur = $Folder

    $guard = 0

 

    while ($null -ne $cur -and $guard -lt 30) {

        $n = ""

        try { $n = (To-TrimmedString $cur.Name) } catch { $n = "" }

        if (-not [string]::IsNullOrWhiteSpace($n)) { $names.Insert(0, $n) }

        try { $cur = $cur.Parent } catch { $cur = $null }

        $guard++

    }

 

    if ($names.Count -eq 0) { return "" }

    return ($names -join "\")

}

 

function Get-InboxFolderDescriptors {

    param(

        [Parameter(Mandatory = $true)]$Namespace,

        [int]$SubfolderDepth = 0

    )

 

    $results = New-Object System.Collections.Generic.List[object]

    $seenIds = New-Object 'System.Collections.Generic.HashSet[string]'

 

    function Add-Folder {

        param($Folder, [string]$StoreName, [int]$Depth)

 

        if ($null -eq $Folder) { return }

 

        $entryId = ""

        try { $entryId = (To-TrimmedString $Folder.EntryID) } catch { $entryId = "" }

 

        if (-not [string]::IsNullOrWhiteSpace($entryId)) {

            if ($seenIds.Contains($entryId)) { return }

            [void]$seenIds.Add($entryId)

        }

 

        $path = ""

        try { $path = Get-OutlookFolderPath -Folder $Folder } catch { $path = "" }

 

        $results.Add([pscustomobject]@{

                Store  = $StoreName

                Folder = $Folder

                Path   = $path

            }) | Out-Null

 

        if ($Depth -le 0) { return }

 

        try {

            $subs = $Folder.Folders

            $subCount = 0

            try { $subCount = [int]$subs.Count } catch { $subCount = 0 }

 

            for ($i = 1; $i -le $subCount; $i++) {

                $sf = $subs.Item($i)

                Add-Folder -Folder $sf -StoreName $StoreName -Depth ($Depth - 1)

            }

        }
        catch { }

    }

 

    $storeCount = 0

    try { $storeCount = [int]$Namespace.Stores.Count } catch { $storeCount = 0 }

 

    if ($storeCount -le 0) {

        $inbox = $null

        try { $inbox = $Namespace.GetDefaultFolder(6) } catch { $inbox = $null }

        Add-Folder -Folder $inbox -StoreName "DefaultStore" -Depth $SubfolderDepth

        return $results

    }

 

    for ($s = 1; $s -le $storeCount; $s++) {

        $store = $null

        try { $store = $Namespace.Stores.Item($s) } catch { $store = $null }

        if ($null -eq $store) { continue }

 

        $storeName = ""

        try { $storeName = (To-TrimmedString $store.DisplayName) } catch { $storeName = "Store$s" }

 

        $inbox = $null

        try { $inbox = $store.GetDefaultFolder(6) } catch { $inbox = $null }

        Add-Folder -Folder $inbox -StoreName $storeName -Depth $SubfolderDepth

    }

 

    return $results

}

 

function Get-LatestAttachmentBySubject {

    param(

        [Parameter(Mandatory = $true)][string]$SubjectKeyword,

        [Parameter(Mandatory = $true)][string]$Label,

        [Parameter(Mandatory = $true)][string]$SaveToFolder,

        [int]$LookbackDays = 14  # kept for compatibility, but NOT used anymore (today-only enforced)

    )

 

    $ctx = "Outlook/$Label"

 

    $outlook = $null

    $ns = $null

    $defaultInbox = $null

 

    # Today-only window (local machine time)

    $dayStart = (Get-Date).Date

    $dayEnd = $dayStart.AddDays(1)

 

    $keywordNorm = Normalize-Text $SubjectKeyword

    Assert-Valid -Condition (-not [string]::IsNullOrWhiteSpace($keywordNorm)) -ErrorMessage "SubjectKeyword is empty after normalization."

 

    try {

        if (-not $ValidateOnly.IsPresent -and -not $WhatIfPreference) {

            if (-not (Test-Path $SaveToFolder)) {

                Invoke-Change -Target $SaveToFolder -Action "Create directory" -ScriptBlock {

                    New-Item -ItemType Directory -Path $SaveToFolder -Force | Out-Null

                } | Out-Null

            }

        }
        else {

            Write-Log -Source $ctx -Message ("PlanOnly: would use attachment folder: {0}" -f $SaveToFolder)

        }

 

        $outlook = New-Object -ComObject Outlook.Application

        $ns = $outlook.GetNamespace("MAPI")

 

        try { $defaultInbox = $ns.GetDefaultFolder(6) } catch { $defaultInbox = $null }

 

        function Try-SearchFolders {

            param(

                [Parameter(Mandatory = $true)]$FolderDescriptors,

                [Parameter(Mandatory = $true)][string]$PassName

            )

 

            Write-Log -Source $ctx -Message ("Pass='{0}' | Folders={1} | DateWindow=[{2} .. {3})" -f `

                $PassName, ($FolderDescriptors | Measure-Object).Count, $dayStart.ToString("yyyy-MM-dd"), $dayEnd.ToString("yyyy-MM-dd"))

 

            foreach ($fd in $FolderDescriptors) {

                $folder = $fd.Folder

                if ($null -eq $folder) { continue }

 

                $itemsAll = $null

                $itemsScan = $null

                $mailItem = $null

                $att = $null

 

                try {

                    $itemsAll = $folder.Items

 

                    # Try to Restrict by date window to reduce scanning.

                    # If Restrict fails (locale quirks), fallback to full scan.

                    $itemsScan = $itemsAll

                    try {

                        $filter = "[ReceivedTime] >= '" + $dayStart.ToString("g") + "' AND [ReceivedTime] < '" + $dayEnd.ToString("g") + "'"

                        $itemsScan = $itemsAll.Restrict($filter)

                    }
                    catch {

                        $itemsScan = $itemsAll

                    }

 

                    $itemsScan.Sort("[ReceivedTime]", $true) | Out-Null

 

                    $count = 0

                    try { $count = [int]$itemsScan.Count } catch { $count = 0 }

 

                    for ($i = 1; $i -le $count; $i++) {

                        $mailItem = $itemsScan.Item($i)

                        if ($null -eq $mailItem) { continue }

 

                        $recv = $null

                        try { $recv = [datetime]$mailItem.ReceivedTime } catch {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                            continue

                        }

 

                        # Enforce TODAY only (defensive even if Restrict worked)

                        if ($recv -ge $dayEnd) {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                            continue

                        }

                        if ($recv -lt $dayStart) {

                            # Sorted desc: once we hit yesterday, stop scanning this folder

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                            break

                        }

 

                        $msgClass = ""

                        try { $msgClass = (To-TrimmedString $mailItem.MessageClass) } catch { $msgClass = "" }

                        if ($msgClass -ne "IPM.Note") {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                            continue

                        }

 

                        $subj = ""

                        try { $subj = (To-TrimmedString $mailItem.Subject) } catch { $subj = "" }

                        if ([string]::IsNullOrWhiteSpace($subj)) {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                            continue

                        }

 

                        $subjNorm = Normalize-Text $subj

                        if ($subjNorm -notlike ("*" + $keywordNorm + "*")) {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                            continue

                        }

 

                        $attCount = 0

                        try { $attCount = [int]$mailItem.Attachments.Count } catch { $attCount = 0 }

                        if ($attCount -lt 1) {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                            continue

                        }

 

                        for ($a = 1; $a -le $attCount; $a++) {

                            $att = $null

                            try {

                                $att = $mailItem.Attachments.Item($a)

                                $attName = (To-TrimmedString $att.FileName)

 

                                if ($attName -match '(?i)\.(csv|xlsx)$') {

                                    $safeAttName = New-SafeFileName -Name $attName

                                    $stamp = $recv.ToString("yyyyMMdd_HHmmss")

                                    $dest = Join-Path $SaveToFolder ("DailyReport_{0}_{1}_{2}_{3}" -f $Label, $stamp, $Script:RunId, $safeAttName)

 

                                    if ($ValidateOnly.IsPresent -or $WhatIfPreference) {

                                        Write-Log -Source $ctx -Message ("PlanOnly: would save attachment to: {0} | Store='{1}' | Folder='{2}' | Subject={3}" -f `

                                            $dest, $fd.Store, $fd.Path, $subj)

                                    }
                                    else {

                                        Invoke-Change -Target $dest -Action "Save attachment" -ScriptBlock {

                                            $att.SaveAsFile($dest)

                                        } | Out-Null

 

                                        Write-Log -Source $ctx -Message ("Saved attachment: {0} | Store='{1}' | Folder='{2}' | Subject={3}" -f `

                                            $dest, $fd.Store, $fd.Path, $subj)

                                    }

 

                                    return [pscustomobject]@{

                                        Path       = $dest

                                        Received   = $recv

                                        FileName   = $attName

                                        Subject    = $subj

                                        Store      = $fd.Store

                                        FolderPath = $fd.Path

                                    }

                                }

                            }
                            finally {

                                if ($att) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$att) }

                            }

                        }

 

                        Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem)

                    }

                }
                catch {

                    Write-Log -Level WARN -Source $ctx -Message ("Folder scan warning (Store='{0}' Folder='{1}'): {2}" -f $fd.Store, $fd.Path, $($_.Exception.Message))

                }
                finally {

                    if ($mailItem) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$mailItem) }

 

                    if ($itemsScan) {

                        # If Restrict created a different Items object, release both

                        if ($itemsAll -and -not [object]::ReferenceEquals($itemsAll, $itemsScan)) {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$itemsScan)

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$itemsAll)

                        }
                        else {

                            Release-ComObjectSafeOnce -ComObjectRef ([ref]$itemsScan)

                            $itemsAll = $null

                        }

                    }
                    elseif ($itemsAll) {

                        Release-ComObjectSafeOnce -ComObjectRef ([ref]$itemsAll)

                    }

 

                    Invoke-GC

                }

            }

 

            return $null

        }

 

        # Pass 1: Default Inbox only

        $defaultDesc = @()

        if ($defaultInbox) {

            $storeName = ""

            try { $storeName = (To-TrimmedString $defaultInbox.Store.DisplayName) } catch { $storeName = "DefaultStore" }

            $defaultDesc += [pscustomobject]@{

                Store  = $storeName

                Folder = $defaultInbox

                Path   = (Get-OutlookFolderPath -Folder $defaultInbox)

            }

        }

 

        $r = $null

        if ($defaultDesc.Count -gt 0) {

            $r = Try-SearchFolders -FolderDescriptors $defaultDesc -PassName "DefaultInbox_TodayOnly"

            if ($r) { return $r }

        }

 

        # Pass 2: All stores, inbox only

        $allInboxDepth0 = Get-InboxFolderDescriptors -Namespace $ns -SubfolderDepth 0

        $r = Try-SearchFolders -FolderDescriptors $allInboxDepth0 -PassName "AllStores_InboxOnly_TodayOnly"

        if ($r) { return $r }

 

        # Pass 3: All stores, inbox + subfolders (depth 2)

        $allInboxDepth2 = Get-InboxFolderDescriptors -Namespace $ns -SubfolderDepth 2

        $r = Try-SearchFolders -FolderDescriptors $allInboxDepth2 -PassName "AllStores_Depth2_TodayOnly"

        if ($r) { return $r }

 

        throw ("No email found with keyword '{0}' received TODAY ({1})." -f $SubjectKeyword, $dayStart.ToString("yyyy-MM-dd"))

    }

    catch {

        Write-Log -Level ERROR -Source $ctx -Message $($_.Exception.Message)

        throw

    }

    finally {

        if ($defaultInbox) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$defaultInbox) }

        if ($ns) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$ns) }

        if ($outlook) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$outlook) }

        Invoke-GC

    }

}

 

# -------------------------

# Read tables (CSV / XLSX)

# -------------------------

function Read-ExcelViaCom {

    param([Parameter(Mandatory = $true)][string]$Path)

 

    $excel = $null

    $wb = $null

    $ws = $null

    $used = $null

 

    try {

        $excel = New-Object -ComObject Excel.Application

        $excel.Visible = $false

        $excel.DisplayAlerts = $false

 

        $wb = $excel.Workbooks.Open($Path, $false, $true) # UpdateLinks=false, ReadOnly=true

        $ws = $wb.Worksheets.Item(1)

        $used = $ws.UsedRange

 

        $data = $used.Value2

        if ($null -eq $data) { return @() }

        if (-not ($data -is [object[, ]])) { return @() }

 

        $colCount = $data.GetLength(1)

        $rowCount = $data.GetLength(0)

        if ($rowCount -lt 2 -or $colCount -lt 1) { return @() }

 

        $headers = @()

        for ($c = 1; $c -le $colCount; $c++) {

            $h = $data[1, $c]

            $hs = (To-TrimmedString $h)

            if ([string]::IsNullOrWhiteSpace($hs)) { $hs = "Col$c" }

            $headers += $hs

        }

 

        $rows = New-Object System.Collections.Generic.List[object]

        for ($r = 2; $r -le $rowCount; $r++) {

            $obj = [ordered]@{}

            for ($c = 1; $c -le $colCount; $c++) {

                $obj[$headers[$c - 1]] = $data[$r, $c]

            }

            $rows.Add([pscustomobject]$obj) | Out-Null

        }

 

        return $rows

    }

    catch {

        Write-Log -Level ERROR -Source 'Read-ExcelViaCom' -Message $($_.Exception.Message)

        throw

    }

    finally {

        try { if ($wb) { $wb.Close($false) | Out-Null } } catch { }

        try { if ($excel) { $excel.Quit() } } catch { }

 

        if ($used) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$used) }

        if ($ws) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$ws) }

        if ($wb) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$wb) }

        if ($excel) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$excel) }

 

        Invoke-GC

    }

}

 

function Read-Table {

    param([Parameter(Mandatory = $true)][string]$Path)

 

    $ext = [IO.Path]::GetExtension($Path).ToLowerInvariant()

    Write-Log -Source 'Read-Table' -Message ("Reading: {0}" -f $Path)

 

    if ($ext -eq '.csv') {

        return Import-CsvUtf8 -Path $Path

    }

    elseif ($ext -eq '.xlsx') {

        return Read-ExcelViaCom -Path $Path

    }

    else {

        throw ("Unsupported file type: {0}" -f $ext)

    }

}

 

# -------------------------

# Dataset normalization

# -------------------------

function Read-Dataset {

    param(

        [Parameter(Mandatory = $true)][string]$Path,

        [Parameter(Mandatory = $true)][string]$SourceLabel

    )

 

    $raw = Read-Table -Path $Path

    $rc = Get-RowCount $raw

    Assert-Valid -Condition ($rc -gt 0) -ErrorMessage ("Empty dataset for {0}: {1}" -f $SourceLabel, $Path)

 

    $sample = $raw | Select-Object -First 1

 

    $colNumber = Find-ColumnName -SampleRow $sample -Candidates @('number')

    $colAssigned = Find-ColumnName -SampleRow $sample -Candidates @('assigned to')

    $colOpened = Find-ColumnName -SampleRow $sample -Candidates @('opened')

    $colState = Find-ColumnName -SampleRow $sample -Candidates @('state')

 

    Assert-Valid -Condition ([bool]$colNumber)   -ErrorMessage ("Column 'Number' not found in {0}" -f $Path)

    Assert-Valid -Condition ([bool]$colAssigned) -ErrorMessage ("Column 'Assigned to' not found in {0}" -f $Path)

    Assert-Valid -Condition ([bool]$colOpened)   -ErrorMessage ("Column 'Opened' not found in {0}" -f $Path)

    Assert-Valid -Condition ([bool]$colState)    -ErrorMessage ("Column 'State' not found in {0}" -f $Path)

 

    Write-Log -Source 'Read-Dataset' -Message ("{0} columns: Number='{1}', Assigned='{2}', Opened='{3}', State='{4}'" -f `

        $SourceLabel, $colNumber, $colAssigned, $colOpened, $colState)

 

    $rows = New-Object System.Collections.Generic.List[object]

    foreach ($r in $raw) {

        $num = (To-TrimmedString $r.$colNumber)

        if ([string]::IsNullOrWhiteSpace($num)) { continue }

 

        $assigned = (To-TrimmedString $r.$colAssigned)

        $openedDt = Parse-DateSafe $r.$colOpened

        $stateOrg = (To-TrimmedString $r.$colState)

 

        $rows.Add([pscustomobject]@{

                number        = $num

                assigned_to   = $assigned

                assigned_norm = (Normalize-AnalystKey $assigned)

                opened_dt     = $openedDt

                stateoriginal = $stateOrg

                state         = (Normalize-State $stateOrg)

                source        = $SourceLabel

            }) | Out-Null

    }

 

    Write-Log -Source 'Read-Dataset' -Message ("{0} rows normalized: {1}" -f $SourceLabel, $rows.Count)

    return $rows

}

 

# -------------------------

# Dedup by ticket number (v5.2)

# -------------------------

function Deduplicate-RowsByNumber {

    param([Parameter(Mandatory = $true)]$Rows)

 

    $groups = $Rows | Group-Object -Property number

    $out = New-Object System.Collections.Generic.List[object]

    $dupsRemoved = 0

 

    foreach ($g in $groups) {

        if ($g.Count -eq 1) {

            $out.Add($g.Group[0]) | Out-Null

            continue

        }

 

        $dupsRemoved += ($g.Count - 1)

 

        $best = $g.Group | Sort-Object `

        @{ Expression = { switch ($($_.state)) { 'Closed' { 3 } 'Pending' { 2 } default { 1 } } }; Descending = $true }, `

        @{ Expression = { if ($($_.opened_dt)) { [datetime]$($_.opened_dt) } else { [datetime]'1900-01-01' } }; Descending = $false } |

        Select-Object -First 1

 

        # Ensure opened_dt is not lost if best is missing a date

        if (-not $best.opened_dt) {

            $earliest = $g.Group | Where-Object { $null -ne $($_.opened_dt) } | Sort-Object opened_dt | Select-Object -First 1

            if ($earliest) { $best.opened_dt = $earliest.opened_dt }

        }

 

        $out.Add($best) | Out-Null

    }

 

    Write-Log -Source 'Dedup' -Message ("Tickets={0} | InputRows={1} | OutputRows={2} | DuplicatesRemoved={3}" -f `

        $groups.Count, (Get-RowCount $Rows), $out.Count, $dupsRemoved)

 

    return $out

}

 

# -------------------------

# Team mapping (cache + token match + fuzzy)

# -------------------------

function Load-TeamMapping {

    param([Parameter(Mandatory = $true)][string]$MapPath)

 

    $map = @{}

    foreach ($row in (Import-CsvUtf8 -Path $MapPath)) {

        $u = Normalize-AnalystKey (To-TrimmedString $row.assigned_to)

        $t = (To-TrimmedString $row.team)

        if (-not [string]::IsNullOrWhiteSpace($u) -and -not [string]::IsNullOrWhiteSpace($t)) {

            $map[$u] = $t

        }

    }

 

    Assert-Valid -Condition ($map.Count -gt 0) -ErrorMessage ("Teams mapping is empty after normalization: {0}" -f $MapPath)

    Write-Log -Source 'Load-TeamMapping' -Message ("Loaded team mapping entries: {0}" -f $map.Count)

    return $map

}

 

# v5.2: type name unique to avoid collisions across scripts/sessions

if (-not ("DailyReportLevenshtein" -as [type])) {

    Add-Type -TypeDefinition @"

using System;

public static class DailyReportLevenshtein {

    public static int Distance(string s, string t) {

        if (string.IsNullOrEmpty(s)) return string.IsNullOrEmpty(t) ? 0 : t.Length;

        if (string.IsNullOrEmpty(t)) return s.Length;

 

        int n = s.Length;

        int m = t.Length;

        int[,] d = new int[n + 1, m + 1];

 

        for (int i = 0; i <= n; i++) d[i, 0] = i;

        for (int j = 0; j <= m; j++) d[0, j] = j;

 

        for (int i = 1; i <= n; i++) {

            for (int j = 1; j <= m; j++) {

                int cost = (t[j - 1] == s[i - 1]) ? 0 : 1;

                d[i, j] = Math.Min(

                    Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1),

                    d[i - 1, j - 1] + cost

                );

            }

        }

        return d[n, m];

    }

 

    public static double Similarity(string s, string t) {

        int maxLen = Math.Max(s.Length, t.Length);

        if (maxLen == 0) return 1.0;

        return 1.0 - ((double)Distance(s, t) / (double)maxLen);

    }

}

"@

}

 

function Apply-Team {

    param(

        [Parameter(Mandatory = $true)]$Rows,

        [Parameter(Mandatory = $true)]$Map,

        [double]$FuzzyThreshold = 0.90

    )

 

    $mapped = New-Object System.Collections.Generic.List[object]

 

    # Cache: analyst_norm -> team OR "" meaning excluded

    $cache = @{}

    $mapKeys = @($Map.Keys)

 

    # Precompute tokens per map key

    $mapTokens = @{}

    foreach ($k in $mapKeys) { $mapTokens[$k] = Get-NameTokens -NormalizedName $k }

 

    foreach ($r in $Rows) {

        $key = (To-TrimmedString $r.assigned_norm)

        if ([string]::IsNullOrWhiteSpace($key)) { continue }

 

        if ($cache.ContainsKey($key)) {

            $teamCached = $cache[$key]

            if (-not [string]::IsNullOrWhiteSpace($teamCached)) {

                Add-Member -InputObject $r -NotePropertyName Team -NotePropertyValue $teamCached -Force

                $mapped.Add($r) | Out-Null

            }

            continue

        }

 

        # 1) Exact match

        if ($Map.ContainsKey($key)) {

            $team = $Map[$key]

            $cache[$key] = $team

            Add-Member -InputObject $r -NotePropertyName Team -NotePropertyValue $team -Force

            $mapped.Add($r) | Out-Null

            continue

        }

 

        # 2) Token-based match

        $keyTokens = Get-NameTokens -NormalizedName $key

        $keySet = New-Object 'System.Collections.Generic.HashSet[string]'

        foreach ($t in $keyTokens) { [void]$keySet.Add($t) }

 

        $bestTokenMatch = $null

        $bestTokenCount = 0

 

        foreach ($candidate in $mapKeys) {

            $candTokens = $mapTokens[$candidate]

            if ($candTokens.Count -lt 2) { continue }

 

            $allPresent = $true

            foreach ($ct in $candTokens) {

                if (-not $keySet.Contains($ct)) { $allPresent = $false; break }

            }

 

            if ($allPresent) {

                if ($candTokens.Count -gt $bestTokenCount) {

                    $bestTokenCount = $candTokens.Count

                    $bestTokenMatch = $candidate

                }

            }

        }

 

        if ($bestTokenMatch) {

            $team = $Map[$bestTokenMatch]

            $cache[$key] = $team

            Add-Member -InputObject $r -NotePropertyName Team -NotePropertyValue $team -Force

            $mapped.Add($r) | Out-Null

            Write-Log -Level WARN -Source 'Apply-Team' -Message ("Token match: '{0}' -> '{1}'" -f (To-TrimmedString $r.assigned_to), $bestTokenMatch)

            continue

        }

 

        # 3) Fuzzy match (Levenshtein)

        $bestMatch = $null

        $bestScore = 0.0

 

        foreach ($candidate in $mapKeys) {

            $score = [DailyReportLevenshtein]::Similarity($key, $candidate)

            if ($score -gt $bestScore) { $bestScore = $score; $bestMatch = $candidate }

        }

 

        if ($bestScore -ge $FuzzyThreshold -and $bestMatch) {

            $team = $Map[$bestMatch]

            $cache[$key] = $team

            Add-Member -InputObject $r -NotePropertyName Team -NotePropertyValue $team -Force

            $mapped.Add($r) | Out-Null

            Write-Log -Level WARN -Source 'Apply-Team' -Message ("Fuzzy match: '{0}' -> '{1}' (score={2}%)" -f (To-TrimmedString $r.assigned_to), $bestMatch, ([math]::Round($bestScore * 100, 1)))

        }

        else {

            $cache[$key] = ""

            Write-Log -Level WARN -Source 'Apply-Team' -Message ("Excluded unmapped analyst: {0} | key_norm='{1}'" -f (To-TrimmedString $r.assigned_to), $key)

        }

    }

 

    Write-Log -Source 'Apply-Team' -Message ("Mapped rows: {0} / {1}" -f $mapped.Count, (Get-RowCount $Rows))

    return $mapped

}

 

# -------------------------

# KPI computation (v5.2: fast business days)

# -------------------------

function Get-BusinessAgeFast {

    param(

        [Parameter(Mandatory = $true)][datetime]$Opened,

        [Parameter(Mandatory = $true)][datetime]$Now

    )

 

    # day after Opened = day 1; count weekdays through Now.Date.

    $start = $Opened.Date.AddDays(1)

    $end = $Now.Date

 

    if ($end -lt $start) { return 0 }

 

    $totalDays = ($end - $start).Days + 1

    $fullWeeks = [math]::Floor($totalDays / 7)

    $business = [int]($fullWeeks * 5)

 

    $remaining = $totalDays % 7

    $base = $start.AddDays($fullWeeks * 7)

 

    for ($i = 0; $i -lt $remaining; $i++) {

        $dow = $base.AddDays($i).DayOfWeek

        if ($dow -ne 'Saturday' -and $dow -ne 'Sunday') { $business++ }

    }

 

    return $business

}

 

function Compute-KPIs {

    param(

        [Parameter(Mandatory = $true)]$AllRows,

        [Parameter(Mandatory = $true)][int]$BacklogDays,

        [Parameter(Mandatory = $true)][datetime]$RefDate

    )

 

    $byTeam = @{}

    $diag = [pscustomobject]@{ Count = 0; Closed = 0; Pending = 0; Backlog = 0; NoDate = 0; OpenNotOverdue = 0 }

 

    foreach ($r in $AllRows) {

        $diag.Count++

 

        if (-not $r.Team) { continue }

 

        $team = $r.Team

        if (-not $byTeam.ContainsKey($team)) {

            $byTeam[$team] = [pscustomobject]@{

                Team              = $team

                ResolvedClosed    = 0

                TicketsNotOverdue = 0

                InPending         = 0

                Backlog           = 0

                OpenAsCBD         = 0

                PctBacklog        = '0.00%'

            }

        }

 

        $st = (To-TrimmedString $r.state)

        $opened = $r.opened_dt

 

        if (-not $opened) {

            $diag.NoDate++

            $byTeam[$team].TicketsNotOverdue++

            continue

        }

 

        if ($st -eq 'Closed') {

            $byTeam[$team].ResolvedClosed++

            $diag.Closed++

            continue

        }

 

        if ($st -eq 'Pending') {

            $byTeam[$team].InPending++

            $diag.Pending++

            continue

        }

 

        $age = Get-BusinessAgeFast -Opened $opened -Now $RefDate

        if ($age -ge $BacklogDays) {

            $byTeam[$team].Backlog++

            $diag.Backlog++

        }

        else {

            $byTeam[$team].TicketsNotOverdue++

            $diag.OpenNotOverdue++

        }

    }

 

    foreach ($x in $byTeam.Values) {

        $x.OpenAsCBD = $x.TicketsNotOverdue + $x.InPending + $x.Backlog

        $den = $x.ResolvedClosed + $x.OpenAsCBD

        $pct = if ($den -gt 0) { [math]::Round(($x.Backlog / $den) * 100, 2) } else { 0 }

        $x.PctBacklog = ("{0:N2}%" -f $pct)

    }

 

    $tot = [pscustomobject]@{

        Team              = 'TOTAL'

        ResolvedClosed    = ($byTeam.Values | Measure-Object ResolvedClosed -Sum).Sum

        TicketsNotOverdue = ($byTeam.Values | Measure-Object TicketsNotOverdue -Sum).Sum

        InPending         = ($byTeam.Values | Measure-Object InPending -Sum).Sum

        Backlog           = ($byTeam.Values | Measure-Object Backlog -Sum).Sum

        OpenAsCBD         = 0

        PctBacklog        = '0.00%'

    }

 

    $tot.OpenAsCBD = $tot.TicketsNotOverdue + $tot.InPending + $tot.Backlog

    $denTot = $tot.ResolvedClosed + $tot.OpenAsCBD

    $pctTot = if ($denTot -gt 0) { [math]::Round(($tot.Backlog / $denTot) * 100, 2) } else { 0 }

    $tot.PctBacklog = ("{0:N2}%" -f $pctTot)

 

    Write-Log -Source 'Compute-KPIs' -Message ("Diag: Total={0} Closed={1} Pending={2} Backlog={3} OpenNotOverdue={4} NoDate={5}" -f `

        $diag.Count, $diag.Closed, $diag.Pending, $diag.Backlog, $diag.OpenNotOverdue, $diag.NoDate)

 

    return , @($byTeam.Values + $tot)

}

 

# -------------------------

# HTML helpers

# -------------------------

function Build-KpiTableHtml {

    param([Parameter(Mandatory = $true)]$Kpis)

 

    $headers = @('Team', 'Resolved/Closed', 'Open as CBD', 'Tickets not overdue', 'In pending (*)', 'Backlog', '% Backlog')

 

    $sb = New-Object System.Text.StringBuilder

    [void]$sb.AppendLine("<table><thead><tr>")

    foreach ($h in $headers) { [void]$sb.AppendLine("<th>$h</th>") }

    [void]$sb.AppendLine("</tr></thead><tbody>")

 

    foreach ($r in $Kpis) {

        $isTotal = ($r.Team -eq 'TOTAL')

        $cls = if ($isTotal) { " class='total'" } else { "" }

        $bkCls = if ([int]$r.Backlog -gt 0) { " class='alert'" } else { "" }

 

        [void]$sb.AppendLine(("<tr{0}><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td>{5}</td><td{6}>{7}</td><td>{8}</td></tr>" -f `

                $cls, $r.Team, $r.ResolvedClosed, $r.OpenAsCBD, $r.TicketsNotOverdue, $r.InPending, $bkCls, $r.Backlog, $r.PctBacklog))

    }

 

    [void]$sb.AppendLine("</tbody></table>")

    return $sb.ToString()

}

 

function ConvertTo-HtmlEncode {

    param([string]$Text)

    if ($null -eq $Text) { return "" }

    return [System.Net.WebUtility]::HtmlEncode($Text)

}

 

# -------------------------

# Email HTML (Outlook-friendly)

# -------------------------

function Build-EmailButtonHtml {

    param(

        [Parameter(Mandatory = $true)][string]$Url,

        [Parameter(Mandatory = $true)][string]$Text,

 

        [string]$BgColor = "#2a4d8f",

        [string]$TextColor = "#ffffff",

        [string]$BorderColor = "#1f3a6b",

 

        [string]$Padding = "10px 14px",

        [string]$FontSize = "12px",

        [string]$MarginRight = "10px"

    )

 

    $u = ConvertTo-HtmlEncode -Text $Url

    $t = ConvertTo-HtmlEncode -Text $Text

 

    return @"

<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="display:inline-table; margin-right:$MarginRight;">

  <tr>

    <td bgcolor="$BgColor" style="padding:$Padding; border:1px solid $BorderColor;">

      <a href="$u" style="font-family:Segoe UI, Arial, sans-serif; font-size:$FontSize; color:$TextColor; text-decoration:none; font-weight:600; display:inline-block;">

        $t

      </a>

    </td>

  </tr>

</table>

"@

}

 

function Parse-PercentToDouble {

    param([string]$Text)

 

    if ([string]::IsNullOrWhiteSpace($Text)) { return 0.0 }

 

    $s = $Text.Trim()

    $s = $s -replace '%', ''

    $s = $s -replace '[^\d,\.]', ''

    if ([string]::IsNullOrWhiteSpace($s)) { return 0.0 }

 

    if ($s -match ',' -and $s -notmatch '\.') {

        $s = $s.Replace(',', '.')

    }
    else {

        $s = $s.Replace(',', '')

    }

 

    try { return [double]::Parse($s, [System.Globalization.CultureInfo]::InvariantCulture) } catch { return 0.0 }

}

 

function Build-ProgressBarHtml {

    param(

        [Parameter(Mandatory = $true)][double]$Percent,

        [string]$FillColor = "#b00000"

    )

 

    $p = [math]::Round($Percent, 2)

    if ($p -lt 0) { $p = 0 }

    if ($p -gt 100) { $p = 100 }

 

    $filledWidth = [int][math]::Round($p)

    $emptyWidth = 100 - $filledWidth

 

    return @"

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #d0d0d0; background-color:#ffffff;">

  <tr>

    <td style="padding:10px 12px;">

      <div style="font-family:Segoe UI, Arial, sans-serif; font-size:11px; color:#666666; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:6px;">

        Backlog %

      </div>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #cccccc; background-color:#eeeeee;">

        <tr>

          <td width="$filledWidth%" bgcolor="$FillColor" style="height:10px; line-height:10px; font-size:1px;">&nbsp;</td>

          <td width="$emptyWidth%" bgcolor="#eeeeee" style="height:10px; line-height:10px; font-size:1px;">&nbsp;</td>

        </tr>

      </table>

      <div style="font-family:Segoe UI, Arial, sans-serif; font-size:12px; color:#222222; margin-top:6px;">

        <b>$p%</b>

      </div>

    </td>

  </tr>

</table>

"@

}

 

function Build-TldrHtml {

    param([Parameter(Mandatory = $true)]$Kpis)

 

    $tot = $Kpis | Where-Object { $($_.Team) -eq 'TOTAL' } | Select-Object -First 1

    if (-not $tot) { return "" }

 

    $totalBacklog = 0

    try { $totalBacklog = [int]$tot.Backlog } catch { $totalBacklog = 0 }

 

    $pct = Parse-PercentToDouble -Text (To-TrimmedString $tot.PctBacklog)

 

    $teamsWithBacklog = @(

        $Kpis |

        Where-Object { $($_.Team) -ne 'TOTAL' } |

        Where-Object {

            $b = 0

            try { $b = [int]$_.Backlog } catch { $b = 0 }

            return ($b -gt 0)

        }

    )

 

    $teamsCount = ($teamsWithBacklog | Measure-Object).Count

 

    $top3 = @(

        $teamsWithBacklog |

        Sort-Object { [int]$_.Backlog } -Descending |

        Select-Object -First 3

    )

 

    $topText = if (($top3 | Measure-Object).Count -gt 0) {

        ($top3 | ForEach-Object { "{0} ({1})" -f $($_.Team), $($_.Backlog) }) -join "; "

    }
    else {

        "None"

    }

 

    $backlogColor = if ($totalBacklog -gt 0) { "#b00000" } else { "#1b5e20" }

    $pctColor = if ($pct -gt 0) { "#b00000" } else { "#1b5e20" }

 

    $cell = {

        param($label, $value, $valueColor, $valueSize)

 

        @"

<td width="25%" valign="top" style="padding:6px;">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #d0d0d0; background-color:#ffffff;">

    <tr>

      <td style="padding:10px 12px;">

        <div style="font-family:Segoe UI, Arial, sans-serif; font-size:11px; color:#666666; text-transform:uppercase; letter-spacing:0.4px;">

          $(ConvertTo-HtmlEncode -Text $label)

        </div>

        <div style="font-family:Segoe UI, Arial, sans-serif; font-size:$valueSize; font-weight:700; margin-top:5px; color:$valueColor;">

          $(ConvertTo-HtmlEncode -Text $value)

        </div>

      </td>

    </tr>

  </table>

</td>

"@

    }

 

    $c1 = $cell.Invoke("Total Backlog", "$totalBacklog", $backlogColor, "20px")

    $c2 = $cell.Invoke("% Backlog", ("{0}%" -f ([math]::Round($pct, 2))), $pctColor, "20px")

    $c3 = $cell.Invoke("Teams w/ backlog", "$teamsCount", "#222222", "20px")

    $c4 = $cell.Invoke("Top 3 Teams", $topText, "#222222", "12px")

 

    return @"

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 10px 0;">

  <tr>

    $c1

    $c2

    $c3

    $c4

  </tr>

</table>

"@

}

 

function Build-KpiCardsHtml {

    param([Parameter(Mandatory = $true)]$Kpis)

 

    $tot = $Kpis | Where-Object { $($_.Team) -eq 'TOTAL' } | Select-Object -First 1

    if (-not $tot) { return "" }

 

    $backlogInt = 0

    try { $backlogInt = [int]$tot.Backlog } catch { $backlogInt = 0 }

 

    $backlogColor = if ($backlogInt -gt 0) { "#b00000" } else { "#1b5e20" }

 

    $cards = @(

        @{ Label = "Total Closed"; Value = "$($tot.ResolvedClosed)"; ValueColor = "#222222" },

        @{ Label = "Open as CBD"; Value = "$($tot.OpenAsCBD)"; ValueColor = "#222222" },

        @{ Label = "Tickets not overdue"; Value = "$($tot.TicketsNotOverdue)"; ValueColor = "#222222" },

        @{ Label = "In Pending"; Value = "$($tot.InPending)"; ValueColor = "#222222" },

        @{ Label = "Backlog"; Value = "$($tot.Backlog)"; ValueColor = $backlogColor },

        @{ Label = "% Backlog"; Value = "$($tot.PctBacklog)"; ValueColor = $backlogColor }

    )

 

    $cell = {

        param($label, $value, $valueColor)

        @"

<td width="33.33%" valign="top" style="padding:6px;">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #d0d0d0; background-color:#ffffff;">

    <tr>

      <td style="padding:10px 12px;">

        <div style="font-family:Segoe UI, Arial, sans-serif; font-size:11px; color:#666666; text-transform:uppercase; letter-spacing:0.4px;">

          $(ConvertTo-HtmlEncode -Text $label)

        </div>

        <div style="font-family:Segoe UI, Arial, sans-serif; font-size:20px; font-weight:700; margin-top:4px; color:$valueColor;">

          $(ConvertTo-HtmlEncode -Text $value)

        </div>

      </td>

    </tr>

  </table>

</td>

"@

    }

 

    $row1 = ($cell.Invoke($cards[0].Label, $cards[0].Value, $cards[0].ValueColor)) +

    ($cell.Invoke($cards[1].Label, $cards[1].Value, $cards[1].ValueColor)) +

    ($cell.Invoke($cards[2].Label, $cards[2].Value, $cards[2].ValueColor))

 

    $row2 = ($cell.Invoke($cards[3].Label, $cards[3].Value, $cards[3].ValueColor)) +

    ($cell.Invoke($cards[4].Label, $cards[4].Value, $cards[4].ValueColor)) +

    ($cell.Invoke($cards[5].Label, $cards[5].Value, $cards[5].ValueColor))

 

    return @"

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 6px 0;">

  <tr>$row1</tr>

  <tr>$row2</tr>

</table>

"@

}

 

function Build-HighlightsHtml {

    param(

        [Parameter(Mandatory = $true)]$Kpis,

        [Parameter(Mandatory = $true)][int]$BacklogAgeDays

    )

 

    $teamsWithBacklog = @(

        $Kpis |

        Where-Object { $($_.Team) -ne 'TOTAL' } |

        Where-Object {

            $b = 0

            try { $b = [int]$_.Backlog } catch { $b = 0 }

            return ($b -gt 0)

        }

    )

 

    $top3 = @(

        $teamsWithBacklog |

        Sort-Object { [int]$_.Backlog } -Descending |

        Select-Object -First 3

    )

 

    $teamsCount = ($teamsWithBacklog | Measure-Object).Count

 

    $topText = if (($top3 | Measure-Object).Count -gt 0) {

        ($top3 | ForEach-Object { "{0} ({1})" -f $($_.Team), $($_.Backlog) }) -join "; "

    }
    else {

        "None"

    }

 

    return @"

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #d0d0d0; background-color:#ffffff; margin:10px 0 14px 0;">

  <tr>

    <td style="padding:12px 14px;">

      <div style="font-family:Segoe UI, Arial, sans-serif; font-size:13px; font-weight:700; color:#2a4d8f; margin-bottom:6px;">

        Highlights

      </div>

      <ul style="margin:0; padding-left:18px; font-family:Segoe UI, Arial, sans-serif; font-size:12px; color:#222222;">

        <li>Backlog threshold: <b>$BacklogAgeDays</b> business days (Open tickets only).</li>

        <li>Teams with backlog &gt; 0: <b>$teamsCount</b>.</li>

        <li>Top teams by backlog: <b>$(ConvertTo-HtmlEncode -Text $topText)</b>.</li>

      </ul>

    </td>

  </tr>

</table>

"@

}

 

function Build-KpiTableHtmlEmail {

    param([Parameter(Mandatory = $true)]$Kpis)

 

    $headers = @(

        @{ Text = "Team"; Align = "left" },

        @{ Text = "Resolved/Closed"; Align = "center" },

        @{ Text = "Open as CBD"; Align = "center" },

        @{ Text = "Tickets not overdue"; Align = "center" },

        @{ Text = "In pending (*)"; Align = "center" },

        @{ Text = "Backlog"; Align = "center" },

        @{ Text = "% Backlog"; Align = "center" }

    )

 

    $sb = New-Object System.Text.StringBuilder

    [void]$sb.AppendLine("<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='border-collapse:collapse; font-family:Segoe UI, Arial, sans-serif; font-size:12px; background-color:#ffffff;'>")

 

    [void]$sb.AppendLine("<tr>")

    foreach ($h in $headers) {

        $ht = ConvertTo-HtmlEncode -Text $h.Text

        $align = $h.Align

        [void]$sb.AppendLine("<th style='border:1px solid #666666; padding:8px 8px; background-color:#f4f4f4; text-align:$align; font-weight:700;'>$ht</th>")

    }

    [void]$sb.AppendLine("</tr>")

 

    $i = 0

    foreach ($r in $Kpis) {

        $i++

 

        $isTotal = (($r.Team) -eq 'TOTAL')

        $rowBg = if ($isTotal) { "#e9f7ef" } else { if (($i % 2) -eq 0) { "#ffffff" } else { "#fafafa" } }

 

        $backlogInt = 0

        try { $backlogInt = [int]$r.Backlog } catch { $backlogInt = 0 }

 

        $backlogStyle = if ($backlogInt -gt 0) { "color:#b00000; font-weight:700;" } else { "color:#1b5e20; font-weight:700;" }

 

        $teamCell = ConvertTo-HtmlEncode -Text "$($r.Team)"

        $teamWeight = if ($isTotal) { "700" } else { "600" }

 

        [void]$sb.AppendLine("<tr style='background-color:$rowBg;'>")

        [void]$sb.AppendLine("<td style='border:1px solid #666666; padding:7px 8px; text-align:left; font-weight:$teamWeight;'>$teamCell</td>")

 

        $cells = @(

            "$($r.ResolvedClosed)",

            "$($r.OpenAsCBD)",

            "$($r.TicketsNotOverdue)",

            "$($r.InPending)",

            "$($r.Backlog)",

            "$($r.PctBacklog)"

        )

 

        for ($c = 0; $c -lt $cells.Count; $c++) {

            $val = ConvertTo-HtmlEncode -Text $cells[$c]

            if ($c -eq 4) {

                [void]$sb.AppendLine("<td style='border:1px solid #666666; padding:7px 8px; text-align:center; $backlogStyle'>$val</td>")

            }
            else {

                [void]$sb.AppendLine("<td style='border:1px solid #666666; padding:7px 8px; text-align:center;'>$val</td>")

            }

        }

 

        [void]$sb.AppendLine("</tr>")

    }

 

    [void]$sb.AppendLine("</table>")

    return $sb.ToString()

}

 

function Build-EmailHtml {

    param(

        [Parameter(Mandatory = $true)]$Kpis,

        [Parameter(Mandatory = $true)][datetime]$RefDate,

        [Parameter(Mandatory = $true)][string]$AgingUrl,

        [Parameter(Mandatory = $true)][string]$MonthFolderUrl,

        [int]$BacklogAgeDays = 3

    )

 

    $tot = $Kpis | Where-Object { $($_.Team) -eq 'TOTAL' } | Select-Object -First 1

    $totalBacklog = if ($tot) { "$($tot.Backlog)" } else { "N/A" }

    $dateText = $RefDate.ToString("yyyy-MM-dd")

 

    $preheader = "CSO GAM Daily Report $dateText — Total backlog: $totalBacklog"

 

    $btnAgingHeader = Build-EmailButtonHtml -Url $AgingUrl -Text "Aging Tickets" -BgColor "#ffffff" -TextColor "#2a4d8f" -BorderColor "#ffffff" -Padding "8px 12px" -FontSize "12px" -MarginRight "8px"

    $btnMonthHeader = Build-EmailButtonHtml -Url $MonthFolderUrl -Text "Month Folder" -BgColor "#ffffff" -TextColor "#2a4d8f" -BorderColor "#ffffff" -Padding "8px 12px" -FontSize "12px" -MarginRight "0px"

 

    $tldr = Build-TldrHtml -Kpis $Kpis

    $cards = Build-KpiCardsHtml -Kpis $Kpis

    $highlights = Build-HighlightsHtml -Kpis $Kpis -BacklogAgeDays $BacklogAgeDays

    $table = Build-KpiTableHtmlEmail -Kpis $Kpis

 

    $pct = 0.0

    if ($tot) { $pct = Parse-PercentToDouble -Text (To-TrimmedString $tot.PctBacklog) }

    $bar = Build-ProgressBarHtml -Percent $pct -FillColor "#b00000"

 

    return @"

<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport" content="width=device-width, initial-scale=1.0">

<meta name="color-scheme" content="light">

<meta name="supported-color-schemes" content="light">

<title>CSO GAM Daily Report - $dateText</title>

</head>

 

<body style="margin:0; padding:0; background-color:#ffffff;">

  <div style="display:none; font-size:1px; color:#ffffff; line-height:1px; max-height:0px; max-width:0px; opacity:0; overflow:hidden;">

    $(ConvertTo-HtmlEncode -Text $preheader)

  </div>

 

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="background-color:#ffffff;">

    <tr>

      <td align="left" style="padding:0;">

 

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="border-collapse:collapse; background-color:#ffffff;">

 

          <tr>

            <td bgcolor="#2a4d8f" style="padding:16px 18px;">

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">

                <tr>

                  <td valign="top" style="padding-right:10px;">

                    <div style="font-family:Segoe UI, Arial, sans-serif; font-size:20px; font-weight:700; color:#ffffff;">

                      CSO GAM — Daily Report

                    </div>

                    <div style="font-family:Segoe UI, Arial, sans-serif; font-size:12px; color:#dbe6ff; margin-top:5px;">

                      Report date: <b>$dateText</b> &nbsp;|&nbsp; Generated: $($RefDate.ToString("yyyy-MM-dd HH:mm"))

                    </div>

                  </td>

                  <td align="right" valign="middle" style="white-space:nowrap;">

                    $btnAgingHeader

                    $btnMonthHeader

                  </td>

                </tr>

              </table>

            </td>

          </tr>

 

          <tr>

            <td style="padding:14px 18px 8px 18px;">

              <div style="font-family:Segoe UI, Arial, sans-serif; font-size:13px; color:#222222;">

                Hello Team,<br>

                This is the daily report of the CSO GAM service requests and incidents.

              </div>

            </td>

          </tr>

 

          <tr>

            <td style="padding:0 18px;">

              $tldr

            </td>

          </tr>

 

          <tr>

            <td style="padding:0 18px 10px 18px;">

              $bar

            </td>

          </tr>

 

          <tr>

            <td style="padding:0 18px;">

              $cards

            </td>

          </tr>

 

          <tr>

            <td style="padding:0 18px;">

              $highlights

            </td>

          </tr>

 

          <tr>

            <td style="padding:0 18px 8px 18px;">

              <div style="font-family:Segoe UI, Arial, sans-serif; font-size:14px; font-weight:700; color:#2a4d8f; margin:6px 0 8px 0;">

                Detailed Table

              </div>

              $table

            </td>

          </tr>

 

          <tr>

            <td style="padding:12px 18px 18px 18px;">

              <div style="font-family:Segoe UI, Arial, sans-serif; font-size:13px; color:#222222;">

                Please feel free to add any comments or information.<br><br>

                Regards,<br>

                Julian Rivara

              </div>

            </td>

          </tr>

 

        </table>

 

      </td>

    </tr>

  </table>

</body>

</html>

"@

}

 

# -------------------------

# Dashboard HTML

# -------------------------

function Build-DashboardHtml {

    param(

        [Parameter(Mandatory = $true)]$Kpis,

        [Parameter(Mandatory = $true)][datetime]$RefDate

    )

 

    $tot = $Kpis | Where-Object { $($_.Team) -eq 'TOTAL' } | Select-Object -First 1

    $totalBacklog = $tot.Backlog

    $totalClosed = $tot.ResolvedClosed

    $totalPending = $tot.InPending

    $pctBacklog = $tot.PctBacklog

 

    $table = Build-KpiTableHtml -Kpis $Kpis

 

    $html = @"

<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>CSO GAM Daily Dashboard - $($RefDate.ToString("yyyy-MM-dd"))</title>

<style>

body { font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #f4f4f4, #ffffff); color: #222; margin: 0; }

header { background-color: #2a4d8f; color: white; padding: 20px 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }

header h1 { margin: 0; font-size: 26px; }

header p { margin: 5px 0 0 0; font-size: 14px; opacity: 0.9; }

.container { max-width: 1100px; margin: 40px auto; padding: 0 20px; }

.card { background: white; border-radius: 12px; box-shadow: 0 3px 10px rgba(0,0,0,0.1); padding: 25px 30px; margin-bottom: 40px; }

h2 { color: #2a4d8f; border-bottom: 2px solid #ff7f32; padding-bottom: 5px; }

.metric-cards { display: flex; flex-wrap: wrap; justify-content: space-around; margin-bottom: 30px; }

.metric { flex: 1 1 200px; margin: 10px; background: #2a4d8f; color: white; border-radius: 10px; text-align: center; padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.15); }

.metric h3 { margin: 0; font-size: 16px; }

.metric p { font-size: 22px; margin: 8px 0 0 0; font-weight: bold; }

table { border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 13px; }

th, td { border: 1px solid #ccc; text-align: center; padding: 6px; }

th { background-color: #f4f4f4; }

tr.total { background: #e9f7ef; font-weight: 600; }

td.alert { color: #b00000; font-weight: 700; }

footer { text-align: center; color: #888; font-size: 12px; margin: 30px 0; }

</style>

</head>

<body>

<header>

  <h1>CSO GAM Daily Dashboard</h1>

  <p>Generated on $($RefDate.ToString("dddd, MMMM dd, yyyy HH:mm"))</p>

</header>

 

<div class="container">

  <div class="metric-cards">

    <div class="metric"><h3>Total Closed</h3><p>$totalClosed</p></div>

    <div class="metric"><h3>Total Pending</h3><p>$totalPending</p></div>

    <div class="metric"><h3>Backlog</h3><p>$totalBacklog</p></div>

    <div class="metric"><h3>% Backlog</h3><p>$pctBacklog</p></div>

  </div>

 

  <div class="card">

    <h2>Detailed Table</h2>

    $table

  </div>

</div>

 

<footer>

  Generated automatically by DailyReport_v$($Script:Version)

</footer>

</body>

</html>

"@

    return $html

}

 

# -------------------------

# Save outputs

# -------------------------

function Save-Outputs {

    param(

        [Parameter(Mandatory = $true)]$AllRows,

        [Parameter(Mandatory = $true)]$Kpis,

        [Parameter(Mandatory = $true)][string]$EmailHtml

    )

 

    $stamp = (Get-Date -f "yyyyMMdd_HHmmss")

    $detailCsv = Join-Path $Script:OutRoot ("DailyDetail_$stamp.csv")

    $kpiCsv = Join-Path $Script:OutRoot ("DailyKpis_$stamp.csv")

    $htmlFile = Join-Path $Script:OutRoot ("DailyEmailTable_$stamp.html")

 

    if ($ValidateOnly.IsPresent -or $WhatIfPreference) {

        Write-Log -Source 'Save-Outputs' -Message "PlanOnly: skipping file exports."

        return [pscustomobject]@{ Detail = $detailCsv; Kpis = $kpiCsv; Html = $htmlFile }

    }

 

    Invoke-Change -Target $detailCsv -Action "Export CSV" -ScriptBlock {

        $AllRows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $detailCsv

    } | Out-Null

 

    Invoke-Change -Target $kpiCsv -Action "Export CSV" -ScriptBlock {

        $Kpis | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $kpiCsv

    } | Out-Null

 

    Invoke-Change -Target $htmlFile -Action "Write HTML" -ScriptBlock {

        Set-Content -Path $htmlFile -Value $EmailHtml -Encoding UTF8

    } | Out-Null

 

    Write-Log -Source 'Save-Outputs' -Message ("Saved outputs:`n - {0}`n - {1}`n - {2}" -f $detailCsv, $kpiCsv, $htmlFile)

 

    return [pscustomobject]@{

        Detail = $detailCsv

        Kpis   = $kpiCsv

        Html   = $htmlFile

    }

}

 

# -------------------------

# Send email via Outlook

# -------------------------

function Resolve-OutlookAccount {

    param(

        [Parameter(Mandatory = $true)]$OutlookApp,

        [string]$DesiredSmtpAddress

    )

 

    if ([string]::IsNullOrWhiteSpace($DesiredSmtpAddress)) { return $null }

 

    try {

        $accounts = $OutlookApp.Session.Accounts

        for ($i = 1; $i -le $accounts.Count; $i++) {

            $acc = $accounts.Item($i)

            $smtp = ""

            try { $smtp = (To-TrimmedString $acc.SmtpAddress) } catch { $smtp = "" }

            if ($smtp -and ($smtp -ieq $DesiredSmtpAddress)) {

                return $acc

            }

        }

        return $null

    }
    catch {

        Write-Log -Level WARN -Source 'Resolve-OutlookAccount' -Message ("Unable to resolve Outlook account: {0}" -f $($_.Exception.Message))

        return $null

    }

}

 

function Send-ReportEmail {

    param(

        [Parameter(Mandatory = $true)][string]$HtmlBody,

        [Parameter(Mandatory = $true)][string]$Subject,

        [string[]]$ToList,

        [string[]]$CcList,

        [string]$FromSmtp

    )

 

    if ($SkipEmail -or $ValidateOnly.IsPresent -or $WhatIfPreference) {

        Write-Log -Source 'Send-ReportEmail' -Message "Email skipped (SkipEmail, ValidateOnly, or WhatIf)."

        return

    }

 

    $outlook = $null

    $mail = $null

    try {

        $outlook = New-Object -ComObject Outlook.Application

        $mail = $outlook.CreateItem(0)

 

        if ($ToList -and $ToList.Count -gt 0) { $mail.To = ($ToList -join ';') }

        if ($CcList -and $CcList.Count -gt 0) { $mail.CC = ($CcList -join ';') }

 

        $mail.Subject = $Subject

        $mail.HTMLBody = $HtmlBody

 

        $acc = Resolve-OutlookAccount -OutlookApp $outlook -DesiredSmtpAddress $FromSmtp

        if ($acc) {

            $mail.SendUsingAccount = $acc

            Write-Log -Source 'Send-ReportEmail' -Message ("Using From account: {0}" -f (To-TrimmedString $acc.SmtpAddress))

        }
        else {

            Write-Log -Source 'Send-ReportEmail' -Message "Using Outlook default sending account (FromSmtpAddress not set or not found)."

        }

 

        $target = "To=$($mail.To) | Cc=$($mail.CC) | Subject=$Subject"

        if ($PSCmdlet.ShouldProcess($target, "Send Outlook email")) {

            $mail.Send()

            Write-Log -Source 'Send-ReportEmail' -Message ("Email sent. To={0} | Cc={1}" -f (To-TrimmedString $mail.To), (To-TrimmedString $mail.CC))

        }
        else {

            Write-Log -Source 'Send-ReportEmail' -Message ("WhatIf: would send email. {0}" -f $target)

        }

    }

    catch {

        Write-Log -Level ERROR -Source 'Send-ReportEmail' -Message $($_.Exception.Message)

        throw

    }

    finally {

        if ($mail) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$mail) }

        if ($outlook) { Release-ComObjectSafeOnce -ComObjectRef ([ref]$outlook) }

        Invoke-GC

    }

}

 

# -------------------------

# Final summary block

# -------------------------

function Write-FinalSummary {

    param([Parameter(Mandatory = $true)][hashtable]$Summary)

 

    $lines = New-Object System.Collections.Generic.List[string]

    $lines.Add("") | Out-Null

    $lines.Add("========================================") | Out-Null

    $lines.Add("FINAL SUMMARY (DailyReport_v5.2)") | Out-Null

    $lines.Add(("RunId: {0}" -f $Script:RunId)) | Out-Null

    $lines.Add(("Started: {0}" -f $Script:StartTs)) | Out-Null

    $lines.Add(("Ended:   {0}" -f (Get-Date))) | Out-Null

    foreach ($k in $Summary.Keys) {

        $lines.Add(("{0}: {1}" -f $k, $Summary[$k])) | Out-Null

    }

    $lines.Add("========================================") | Out-Null

 

    foreach ($l in $lines) { Add-Content -Path $Script:LogFile -Value $l -Encoding UTF8 }

}

 

# -------------------------

# MAIN

# -------------------------

$exitCode = 0

 

try {

    $ErrorActionPreference = 'Stop'

 

    Initialize-Environment

 

    $inboxSave = Join-Path $Script:OutRoot ("Inbox_" + (Get-Date -f "yyyyMMdd_HHmmss"))

 

    # Outlook intake (Open/Closed)

    $openAtt = Get-LatestAttachmentBySubject -SubjectKeyword $OpenSubjectKeyword   -Label 'Open'   -SaveToFolder $inboxSave -LookbackDays $MailLookbackDays

    $closedAtt = Get-LatestAttachmentBySubject -SubjectKeyword $ClosedSubjectKeyword -Label 'Closed' -SaveToFolder $inboxSave -LookbackDays $MailLookbackDays

 

    # v5.2 behavior: ValidateOnly and WhatIf are plan-only (stop here).

    if ($ValidateOnly.IsPresent -or $WhatIfPreference) {

        Write-Log -Source 'MAIN' -Message "PlanOnly mode: stopping after Outlook search verification."

        $exitCode = 0

    }

    else {

        # Ensure inbox save folder exists now (we will read from disk)

        if (-not (Test-Path $inboxSave)) {

            Invoke-Change -Target $inboxSave -Action "Create directory" -ScriptBlock {

                New-Item -ItemType Directory -Path $inboxSave -Force | Out-Null

            } | Out-Null

        }

 

        # Read datasets

        $openRows = Read-Dataset -Path $openAtt.Path   -SourceLabel 'Open'

        $closedRows = Read-Dataset -Path $closedAtt.Path -SourceLabel 'Closed'

        $allRows = @($openRows + $closedRows)

 

        # Optional dedup

        if (-not $DisableDedup.IsPresent) {

            $allRows = Deduplicate-RowsByNumber -Rows $allRows

        }
        else {

            Write-Log -Source 'Dedup' -Message "Dedup disabled (DisableDedup)."

        }

 

        # Team mapping

        $teamMap = Load-TeamMapping -MapPath $TeamsCsv

        $mapped = Apply-Team -Rows $allRows -Map $teamMap -FuzzyThreshold 0.90

 

        Assert-Valid -Condition ((Get-RowCount $mapped) -gt 0) -ErrorMessage "No rows mapped to teams. Check Teams.csv normalization."

 

        # KPIs

        $refDate = Get-Date

        $kpis = Compute-KPIs -AllRows $mapped -BacklogDays $BacklogAgeDays -RefDate $refDate

        # Sort KPI rows alphabetically by Team, keep TOTAL last

        $kpis = @(

            $kpis | Where-Object { $($_.Team) -ne 'TOTAL' } | Sort-Object -Property Team

        ) + @(

            $kpis | Where-Object { $($_.Team) -eq 'TOTAL' }

        )

 

 

        # Email + dashboard URLs

        $today = Get-Date -Format 'yyyy-MM-dd'

        $monthLabel = Get-Date -Format 'yyyy-MM'

        $yearLabel = Get-Date -Format 'yyyy'

        $monthFolderUrl = ($DashboardSharePointBaseUrl.TrimEnd('/') + "/" + $yearLabel + "/" + $monthLabel + "/")

 

        $emailHtml = Build-EmailHtml -Kpis $kpis -RefDate $refDate -AgingUrl $AgingLink -MonthFolderUrl $monthFolderUrl -BacklogAgeDays $BacklogAgeDays

 

        # Dashboard generation

        $dashboardPath = ""

        $dashboardCopy = ""

 

        if (-not $SkipDashboard) {

            $yearPath = Join-Path $DashboardLocalRoot $yearLabel

            $monthPath = Join-Path $yearPath $monthLabel

 

            if (-not (Test-Path $yearPath)) {

                Invoke-Change -Target $yearPath -Action "Create directory" -ScriptBlock {

                    New-Item -ItemType Directory -Path $yearPath -Force | Out-Null

                } | Out-Null

                Write-Log -Source 'Dashboard' -Message ("Created folder: {0}" -f $yearPath)

            }

            if (-not (Test-Path $monthPath)) {

                Invoke-Change -Target $monthPath -Action "Create directory" -ScriptBlock {

                    New-Item -ItemType Directory -Path $monthPath -Force | Out-Null

                } | Out-Null

                Write-Log -Source 'Dashboard' -Message ("Created folder: {0}" -f $monthPath)

            }

 

            $dashboardHtml = Build-DashboardHtml -Kpis $kpis -RefDate $refDate

            $dashboardFileName = "Dashboard_$today.html"

            $dashboardPath = Join-Path $monthPath $dashboardFileName

 

            Invoke-Change -Target $dashboardPath -Action "Write dashboard HTML" -ScriptBlock {

                Set-Content -Path $dashboardPath -Value $dashboardHtml -Encoding UTF8

            } | Out-Null

            Write-Log -Source 'Dashboard' -Message ("Dashboard saved: {0}" -f $dashboardPath)

 

            $desktopPath = [Environment]::GetFolderPath('Desktop')

            $dashboardCopy = Join-Path $desktopPath "Dashboard_Latest.html"

 

            Invoke-Change -Target $dashboardCopy -Action "Copy dashboard to Desktop" -ScriptBlock {

                Copy-Item -Path $dashboardPath -Destination $dashboardCopy -Force

            } | Out-Null

            Write-Log -Source 'Dashboard' -Message ("Dashboard copied to desktop: {0}" -f $dashboardCopy)

        }
        else {

            Write-Log -Source 'Dashboard' -Message "Dashboard skipped (SkipDashboard)."

        }

 

        # Save outputs

        $outs = Save-Outputs -AllRows $mapped -Kpis $kpis -EmailHtml $emailHtml

 

        # Send email

        $subject = "Daily Report - $today"

        Send-ReportEmail -HtmlBody $emailHtml -Subject $subject -ToList $To -CcList $Cc -FromSmtp $FromSmtpAddress

 

        # Summary

        $totRow = $kpis | Where-Object { $($_.Team) -eq 'TOTAL' } | Select-Object -First 1

        $summary = @{

            "Open attachment"   = $openAtt.Path

            "Closed attachment" = $closedAtt.Path

            "Rows (all)"        = (Get-RowCount $allRows)

            "Rows (mapped)"     = (Get-RowCount $mapped)

            "BacklogAgeDays"    = $BacklogAgeDays

            "TOTAL backlog"     = $totRow.Backlog

            "TOTAL pct backlog" = $totRow.PctBacklog

            "Outputs.DetailCsv" = $outs.Detail

            "Outputs.KpisCsv"   = $outs.Kpis

            "Outputs.EmailHtml" = $outs.Html

            "Dashboard path"    = $dashboardPath

            "Dashboard desktop" = $dashboardCopy

            "Email sent"        = (-not $SkipEmail)

            "Dedup enabled"     = (-not $DisableDedup.IsPresent)

        }

        Write-FinalSummary -Summary $summary

 

        Write-Log -Source 'MAIN' -Message "Run OK"

        $exitCode = 0

    }

}

catch {

    Write-Log -Level ERROR -Source 'MAIN' -Message $($_.Exception.Message)

    $exitCode = 1

}

finally {

    $elapsed = (Get-Date) - $Script:StartTs

    Write-Log -Source 'MAIN' -Message ("End. Duration: {0:hh\:mm\:ss}" -f $elapsed)

 

    if ($OpenLog) {

        Start-Process $Script:LogFile

    }

 

    exit $exitCode

}

 