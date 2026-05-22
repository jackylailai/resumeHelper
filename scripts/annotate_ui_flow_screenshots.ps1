param(
    [string]$AssetsDir = "docs\assets\ui-flow"
)

Add-Type -AssemblyName System.Drawing

$root = Resolve-Path -LiteralPath (Join-Path (Get-Location) $AssetsDir)

function New-Annotation {
    param(
        [int]$X,
        [int]$Y,
        [int]$W,
        [int]$H,
        [int]$LabelX,
        [int]$LabelY,
        [int]$LabelW,
        [int]$LabelH,
        [string]$Text
    )
    [pscustomobject]@{
        X = $X; Y = $Y; W = $W; H = $H
        LabelX = $LabelX; LabelY = $LabelY; LabelW = $LabelW; LabelH = $LabelH
        Text = $Text
    }
}

function Convert-Label {
    param([string]$Text)
    [System.Net.WebUtility]::HtmlDecode($Text)
}

function Draw-WrappedText {
    param(
        [System.Drawing.Graphics]$Graphics,
        [string]$Text,
        [System.Drawing.Font]$Font,
        [System.Drawing.Brush]$Brush,
        [System.Drawing.RectangleF]$Bounds,
        [System.Drawing.StringFormat]$Format
    )
    $Graphics.DrawString($Text, $Font, $Brush, $Bounds, $Format)
}

function Save-LabeledImage {
    param(
        [string]$SourceName,
        [string]$DestinationName,
        [array]$Annotations
    )

    $source = Join-Path $root $SourceName
    $destination = Join-Path $root $DestinationName
    $img = [System.Drawing.Image]::FromFile($source)
    $bmp = $null
    $graphics = $null

    try {
        $bmp = New-Object System.Drawing.Bitmap $img.Width, $img.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bmp)
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
        $graphics.DrawImage($img, 0, 0, $img.Width, $img.Height)

        $targetPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 251, 191, 36)), 4
        $targetFill = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(28, 251, 191, 36))
        $labelFill = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(238, 15, 23, 42))
        $labelPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 251, 191, 36)), 3
        $linePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 251, 191, 36)), 2
        $textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
        $font = New-Object System.Drawing.Font "Microsoft JhengHei UI", 15, ([System.Drawing.FontStyle]::Bold)
        $format = New-Object System.Drawing.StringFormat
        $format.Alignment = [System.Drawing.StringAlignment]::Near
        $format.LineAlignment = [System.Drawing.StringAlignment]::Center
        $format.Trimming = [System.Drawing.StringTrimming]::EllipsisWord

        foreach ($a in $Annotations) {
            $target = New-Object System.Drawing.Rectangle $a.X, $a.Y, $a.W, $a.H
            $label = New-Object System.Drawing.Rectangle $a.LabelX, $a.LabelY, $a.LabelW, $a.LabelH
            $labelText = New-Object System.Drawing.RectangleF (
                [single]($a.LabelX + 12),
                [single]($a.LabelY + 6),
                [single]($a.LabelW - 24),
                [single]($a.LabelH - 12)
            )

            $graphics.FillRectangle($targetFill, $target)
            $graphics.DrawRectangle($targetPen, $target)
            $graphics.FillRectangle($labelFill, $label)
            $graphics.DrawRectangle($labelPen, $label)

            $targetCenterX = $a.X + [int]($a.W / 2)
            $targetCenterY = $a.Y + [int]($a.H / 2)
            $labelCenterX = $a.LabelX + [int]($a.LabelW / 2)
            $labelCenterY = $a.LabelY + [int]($a.LabelH / 2)
            $graphics.DrawLine($linePen, $labelCenterX, $labelCenterY, $targetCenterX, $targetCenterY)

            Draw-WrappedText $graphics $a.Text $font $textBrush $labelText $format
        }

        $bmp.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        if ($graphics) { $graphics.Dispose() }
        if ($bmp) { $bmp.Dispose() }
        $img.Dispose()
    }
}

$evaluate = @(
    New-Annotation 324 94 852 214 50 90 260 64 "1. Confirm the app is ready"
    New-Annotation 344 365 812 45 60 350 240 64 "2. Pick the resume profile"
    New-Annotation 344 444 812 186 58 460 250 64 "3. Paste the job description"
    New-Annotation 344 649 230 35 60 640 230 64 "4. Run the scoring"
    New-Annotation 344 735 832 350 60 760 260 64 "5. Read score, gaps, next step"
)

$profile = @(
    New-Annotation 1051 115 105 27 795 104 240 64 "1. Start a new profile"
    New-Annotation 344 337 812 41 58 330 230 64 "2. Name this resume"
    New-Annotation 344 399 348 33 58 395 275 64 "3. Upload PDF, then preview"
    New-Annotation 344 478 812 168 58 500 260 64 "4. Check extracted skills"
    New-Annotation 344 662 170 20 58 640 260 64 "5. Use it by default"
    New-Annotation 344 695 124 33 58 705 240 64 "6. Save and return to list"
)

$jdDatabase = @(
    New-Annotation 121 231 1037 96 40 230 250 64 "1. Find jobs to review"
    New-Annotation 121 329 430 96 40 330 250 64 "2. Choose scoring profile"
    New-Annotation 121 886 382 775 40 1030 250 64 "3. Tick jobs to score"
    New-Annotation 842 383 137 42 1010 360 190 64 "4. Score them"
    New-Annotation 121 443 1037 120 40 460 260 64 "5. Check score results"
    New-Annotation 522 886 635 775 900 800 260 64 "6. Open full JD details"
)

$history = @(
    New-Annotation 1104 94 72 27 840 88 245 64 "1. Reload latest scores"
    New-Annotation 324 258 852 108 60 280 260 64 "2. Find by score status"
    New-Annotation 1091 328 53 25 840 315 245 64 "3. Open full details"
)

$submittable = @(
    New-Annotation 1103 94 72 27 845 88 240 64 "1. Reload ready resumes"
    New-Annotation 324 135 852 78 60 150 265 64 "2. Pick resume to review"
    New-Annotation 1030 177 53 25 765 166 230 64 "3. Read resume text"
    New-Annotation 1092 177 49 25 875 232 230 64 "4. Download PDF"
)

$applications = @(
    New-Annotation 122 246 1036 100 60 250 250 64 "1. Search tracked jobs"
    New-Annotation 122 365 1036 222 60 430 270 64 "2. Review opportunity row"
    New-Annotation 697 514 187 45 450 508 230 64 "3. Update pipeline status"
    New-Annotation 906 514 225 45 880 610 260 64 "4. Set next follow-up date"
)

Save-LabeledImage "evaluate-result.png" "evaluate-result.labeled.png" $evaluate
Save-LabeledImage "profile-add-form.png" "profile-add-form.labeled.png" $profile
Save-LabeledImage "jd-batch-result.png" "jd-batch-result.labeled.png" $jdDatabase
Save-LabeledImage "history.png" "history.labeled.png" $history
Save-LabeledImage "submittable.png" "submittable.labeled.png" $submittable
Save-LabeledImage "applications-updated.png" "applications-updated.labeled.png" $applications

$evaluateZh = @(
    New-Annotation 324 94 852 214 50 90 260 64 (Convert-Label "1. &#x78BA;&#x8A8D;&#x7CFB;&#x7D71;&#x53EF;&#x7528;")
    New-Annotation 344 365 812 45 60 350 240 64 (Convert-Label "2. &#x9078;&#x5C65;&#x6B77; Profile")
    New-Annotation 344 444 812 186 58 460 250 64 (Convert-Label "3. &#x8CBC;&#x4E0A;&#x8077;&#x7F3A; JD")
    New-Annotation 344 649 230 35 60 640 230 64 (Convert-Label "4. &#x958B;&#x59CB;&#x8A55;&#x5206;")
    New-Annotation 344 735 832 350 60 760 260 64 (Convert-Label "5. &#x770B;&#x5206;&#x6578;&#x8207;&#x7F3A;&#x53E3;")
)

$profileZh = @(
    New-Annotation 1051 115 105 27 795 104 240 64 (Convert-Label "1. &#x65B0;&#x589E; Profile")
    New-Annotation 344 337 812 41 58 330 230 64 (Convert-Label "2. &#x547D;&#x540D;&#x5C65;&#x6B77;&#x7248;&#x672C;")
    New-Annotation 344 399 348 33 58 395 275 64 (Convert-Label "3. &#x4E0A;&#x50B3; PDF/&#x9810;&#x89BD;")
    New-Annotation 344 478 812 168 58 500 260 64 (Convert-Label "4. &#x78BA;&#x8A8D;&#x6280;&#x80FD;&#x6587;&#x5B57;")
    New-Annotation 344 662 170 20 58 640 260 64 (Convert-Label "5. &#x8A2D;&#x6210;&#x9810;&#x8A2D;")
    New-Annotation 344 695 124 33 58 705 240 64 (Convert-Label "6. &#x5132;&#x5B58; Profile")
)

$jdDatabaseZh = @(
    New-Annotation 121 231 1037 96 40 230 250 64 (Convert-Label "1. &#x641C;&#x5C0B;&#x8077;&#x7F3A;")
    New-Annotation 121 329 430 96 40 330 250 64 (Convert-Label "2. &#x9078;&#x8A55;&#x5206; Profile")
    New-Annotation 121 886 382 775 40 1030 250 64 (Convert-Label "3. &#x52FE;&#x9078;&#x8077;&#x7F3A;")
    New-Annotation 842 383 137 42 1010 360 190 64 (Convert-Label "4. &#x6279;&#x6B21;&#x8A55;&#x5206;")
    New-Annotation 121 443 1037 120 40 460 260 64 (Convert-Label "5. &#x770B;&#x8A55;&#x5206;&#x7D50;&#x679C;")
    New-Annotation 522 886 635 775 900 800 260 64 (Convert-Label "6. &#x6253;&#x958B;&#x5B8C;&#x6574; JD")
)

$historyZh = @(
    New-Annotation 1104 94 72 27 840 88 245 64 (Convert-Label "1. &#x91CD;&#x65B0;&#x6574;&#x7406;&#x7D00;&#x9304;")
    New-Annotation 324 258 852 108 60 280 260 64 (Convert-Label "2. &#x4F9D;&#x72C0;&#x614B;&#x627E;&#x7D50;&#x679C;")
    New-Annotation 1091 328 53 25 840 315 245 64 (Convert-Label "3. &#x67E5;&#x770B;&#x8A73;&#x60C5;")
)

$submittableZh = @(
    New-Annotation 1103 94 72 27 845 88 240 64 (Convert-Label "1. &#x66F4;&#x65B0;&#x5F85;&#x6295;&#x905E;&#x5C65;&#x6B77;")
    New-Annotation 324 135 852 78 60 150 265 64 (Convert-Label "2. &#x9078;&#x5C65;&#x6B77;&#x6AA2;&#x67E5;")
    New-Annotation 1030 177 53 25 765 166 230 64 (Convert-Label "3. &#x67E5;&#x770B;&#x5C65;&#x6B77;&#x6587;&#x5B57;")
    New-Annotation 1092 177 49 25 875 232 230 64 (Convert-Label "4. &#x4E0B;&#x8F09; PDF")
)

$applicationsZh = @(
    New-Annotation 122 246 1036 100 60 250 250 64 (Convert-Label "1. &#x641C;&#x5C0B;&#x8FFD;&#x8E64;&#x6E05;&#x55AE;")
    New-Annotation 122 365 1036 222 60 430 270 64 (Convert-Label "2. &#x6AA2;&#x67E5;&#x6A5F;&#x6703;&#x8CC7;&#x6599;")
    New-Annotation 697 514 187 45 450 508 230 64 (Convert-Label "3. &#x66F4;&#x65B0;&#x6295;&#x905E;&#x72C0;&#x614B;")
    New-Annotation 906 514 225 45 880 610 260 64 (Convert-Label "4. &#x8A2D;&#x8FFD;&#x8E64;&#x65E5;&#x671F;")
)

Save-LabeledImage "evaluate-result.png" "evaluate-result.zh-TW.labeled.png" $evaluateZh
Save-LabeledImage "profile-add-form.png" "profile-add-form.zh-TW.labeled.png" $profileZh
Save-LabeledImage "jd-batch-result.png" "jd-batch-result.zh-TW.labeled.png" $jdDatabaseZh
Save-LabeledImage "history.png" "history.zh-TW.labeled.png" $historyZh
Save-LabeledImage "submittable.png" "submittable.zh-TW.labeled.png" $submittableZh
Save-LabeledImage "applications-updated.png" "applications-updated.zh-TW.labeled.png" $applicationsZh

Write-Host "Wrote labeled UI flow screenshots to $root"
