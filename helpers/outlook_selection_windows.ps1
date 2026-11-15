# Read only the selected Internet Message-IDs from an existing Classic Outlook.
# No mail contents, sending, mailbox edits, or new Outlook instance.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$outlook = $null
$explorer = $null
$selection = $null
$errorCode = 'unavailable'
$failed = $false
try {
    $outlook = [Runtime.InteropServices.Marshal]::GetActiveObject('Outlook.Application')
    $explorer = $outlook.ActiveExplorer()
    if ($null -eq $explorer) { $errorCode = 'empty'; throw 'empty' }
    $selection = $explorer.Selection
    if ($selection.Count -eq 0) { $errorCode = 'empty'; throw 'empty' }
    if ($selection.Count -gt 500) { $errorCode = 'too_many'; throw 'too_many' }
    $ids = [System.Collections.Generic.List[string]]::new()
    for ($index = 1; $index -le $selection.Count; $index++) {
        $item = $null
        $accessor = $null
        try {
            $item = $selection.Item($index)
            if ($item.Class -ne 43) { $errorCode = 'not_mail'; throw 'not_mail' }
            $accessor = $item.PropertyAccessor
            $errorCode = 'missing_id'
            try { $value = $accessor.GetProperty('http://schemas.microsoft.com/mapi/proptag/0x1035001F') }
            catch { $value = $accessor.GetProperty('http://schemas.microsoft.com/mapi/proptag/0x1035001E') }
            if ([string]::IsNullOrWhiteSpace($value)) { throw 'missing_id' }
            $ids.Add($value.Trim())
        } finally {
            if ($null -ne $accessor) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($accessor) }
            if ($null -ne $item) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($item) }
        }
    }
    @{ ids = @($ids.ToArray()) } | ConvertTo-Json -Compress
} catch {
    # Never print provider exceptions or selected mail details.
    @{ error = $errorCode } | ConvertTo-Json -Compress
    $failed = $true
} finally {
    if ($null -ne $selection) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($selection) }
    if ($null -ne $explorer) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($explorer) }
    if ($null -ne $outlook) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($outlook) }
}
if ($failed) { exit 1 }
