#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$StatusFile
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "SilentlyContinue"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = "X-Amplicon"
$form.Width = 430
$form.Height = 220
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.ControlBox = $false
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(250, 252, 255)

$badge = New-Object System.Windows.Forms.Label
$badge.Text = "X"
$badge.Left = 28
$badge.Top = 28
$badge.Width = 54
$badge.Height = 54
$badge.TextAlign = "MiddleCenter"
$badge.Font = New-Object System.Drawing.Font("Segoe UI", 24, [System.Drawing.FontStyle]::Bold)
$badge.ForeColor = [System.Drawing.Color]::White
$badge.BackColor = [System.Drawing.Color]::FromArgb(28, 116, 140)

$title = New-Object System.Windows.Forms.Label
$title.Text = "X-Amplicon"
$title.Left = 98
$title.Top = 28
$title.Width = 290
$title.Height = 30
$title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(24, 36, 48)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "16S Amplicon Analysis Assistant"
$subtitle.Left = 100
$subtitle.Top = 60
$subtitle.Width = 290
$subtitle.Height = 24
$subtitle.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(80, 96, 112)

$status = New-Object System.Windows.Forms.Label
$status.Text = "Starting Web UI..."
$status.Left = 30
$status.Top = 110
$status.Width = 360
$status.Height = 24
$status.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$status.ForeColor = [System.Drawing.Color]::FromArgb(35, 47, 60)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Left = 30
$progress.Top = 142
$progress.Width = 360
$progress.Height = 12
$progress.Style = "Marquee"
$progress.MarqueeAnimationSpeed = 35

$footer = New-Object System.Windows.Forms.Label
$footer.Text = "Author: XinXi Xu"
$footer.Left = 30
$footer.Top = 166
$footer.Width = 360
$footer.Height = 20
$footer.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$footer.ForeColor = [System.Drawing.Color]::FromArgb(110, 122, 135)

$form.Controls.AddRange(@($badge, $title, $subtitle, $status, $progress, $footer))

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 300
$timer.Add_Tick({
    if (-not (Test-Path -LiteralPath $StatusFile)) {
        return
    }
    $raw = Get-Content -LiteralPath $StatusFile -Raw
    if (-not $raw) {
        return
    }
    $raw = $raw.Trim()
    if ($raw -eq "CLOSE") {
        $timer.Stop()
        $form.Close()
        return
    }
    if ($raw.StartsWith("STATUS|")) {
        $status.Text = $raw.Substring(7)
    }
})

$form.Add_Shown({
    $timer.Start()
})

[System.Windows.Forms.Application]::Run($form)
