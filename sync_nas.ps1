# Sincroniza la copia de trabajo con el NAS (Y:\Mi software\Hasher).
# Sincronización aditiva: copia lo nuevo o modificado y no borra nada en Y:.
# Tras mover o eliminar ficheros aquí, limpiar los huérfanos de Y: a mano.
$src = $PSScriptRoot
$dst = "Y:\Mi software\Hasher"

if (-not (Test-Path "Y:\Mi software")) { throw "No se encuentra Y:\Mi software (¿NAS desconectado?)" }
robocopy $src $dst /E /R:1 /W:1 /NP /NFL /NDL /NJH
if ($LASTEXITCODE -ge 8) { throw "robocopy terminó con error $LASTEXITCODE" }
Write-Host "Sincronizado con $dst"
exit 0
