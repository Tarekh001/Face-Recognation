$f = "C:\Users\ASUS\Web_Face_Recognation\src\pages\JadwalKegiatan.jsx"
$lines = [System.IO.File]::ReadAllLines($f)
Write-Host "Total lines before: $($lines.Count)"

# Keep lines 0-673 (1-674) = clean code up to new OPD selector </div>
# Skip lines 674-751 (1-indexed 675-752) = old pegawai NIP selector + old super admin info
# Keep lines 752-766 (1-indexed 753-767) = Submit button + form close + modal close
# Skip lines 767-884 (1-indexed 768-885) = old assignment modal
# Keep lines 885+ (1-indexed 886+) = </main>, component close, export
$keep = @()
$keep += $lines[0..673]
$keep += $lines[752..766]
$keep += $lines[885..($lines.Count-1)]

Write-Host "Total lines after: $($keep.Count)"
[System.IO.File]::WriteAllLines($f, $keep)
Write-Host "Done!"
