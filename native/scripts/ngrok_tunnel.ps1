param([ValidateSet('start','status','stop')][string]$Action='status')
$ErrorActionPreference='Stop'
$lensRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$lensPrivate=Join-Path $lensRoot 'runtime\ngrok-private'
$lensExe=Join-Path $lensRoot 'runtime\network-tools\ngrok.exe'
$lensReceipt=Join-Path $lensPrivate 'tunnel.json'
$lensDomain='https://outreach-alibi-reformer.ngrok-free.dev'
$lensProcess=$null
if(Test-Path -LiteralPath $lensReceipt){
    $lensState=Get-Content -LiteralPath $lensReceipt -Raw | ConvertFrom-Json
    $lensCandidate=Get-Process -Id $lensState.pid -ErrorAction SilentlyContinue
    if($lensCandidate -and $lensCandidate.Path -eq $lensExe -and $lensCandidate.StartTime.ToUniversalTime().Ticks.ToString() -eq $lensState.startTicks){$lensProcess=$lensCandidate}
}
if($Action -eq 'status'){
    [pscustomobject]@{processRunning=($null -ne $lensProcess);url=$lensDomain;httpsAcceptanceRequired=$true}|ConvertTo-Json
    exit 0
}
if($Action -eq 'stop'){
    if($lensProcess){Stop-Process -Id $lensProcess.Id -ErrorAction Stop}
    Write-Output 'Matching tunnel process stopped or already absent; backend was not stopped.'
    exit 0
}
if($lensProcess){Write-Output 'Tunnel process already running; check public HTTPS acceptance.';exit 0}
if((Get-FileHash -LiteralPath $lensExe -Algorithm SHA256).Hash -ne 'D339BCBD0713233337E860163F5249EEA679CF26750A5700510DBC241D201748'){throw 'ngrok executable changed; reverify official release before starting.'}
$lensSignature=Get-AuthenticodeSignature -LiteralPath $lensExe
if($lensSignature.Status -ne 'Valid' -or $lensSignature.SignerCertificate.Subject -notmatch 'ngrok'){throw 'Valid ngrok publisher signature required.'}
$lensHealth=Invoke-RestMethod -Uri 'http://127.0.0.1:4318/api/native/health' -TimeoutSec 5
if($lensHealth.status -ne 'ok'){throw 'PC backend health check failed.'}
$lensSecure=$null
$lensOldToken=$env:NGROK_AUTHTOKEN
try{
    $lensSecure=Get-Content -LiteralPath (Join-Path $lensPrivate 'authtoken.dpapi') -Raw | ConvertTo-SecureString
    $lensCredential=New-Object System.Net.NetworkCredential('', $lensSecure)
    $env:NGROK_AUTHTOKEN=$lensCredential.Password
    $lensConfig=Join-Path $lensRoot 'native\deploy\ngrok-agent.yml'
    $lensInfo=New-Object System.Diagnostics.ProcessStartInfo
    $lensInfo.FileName=$lensExe
    $lensInfo.Arguments='http http://127.0.0.1:4318 --url='+$lensDomain+' --inspect=false --log=false --config="'+$lensConfig+'"'
    $lensInfo.UseShellExecute=$false
    $lensInfo.CreateNoWindow=$true
    $lensInfo.RedirectStandardError=$true
    # ERR_NGROK_9009: free agent cannot inherit an HTTP proxy. Child only.
    foreach($lensProxyName in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy_env','NGROK_PROXY_URL')){
        $lensInfo.EnvironmentVariables.Remove($lensProxyName)
    }
    $lensProcess=[Diagnostics.Process]::Start($lensInfo)
    $lensStartTicks=$lensProcess.StartTime.ToUniversalTime().Ticks.ToString()
}finally{
    $env:NGROK_AUTHTOKEN=$lensOldToken
    $lensCredential=$null
    if($lensSecure){$lensSecure.Dispose()}
}
Start-Sleep -Seconds 3
$lensProcess.Refresh()
if($lensProcess.HasExited){
    $lensFailure=$lensProcess.StandardError.ReadToEnd()
    $lensCodes=@([regex]::Matches($lensFailure,'ERR_NGROK_[0-9]+')|ForEach-Object{$_.Value}|Select-Object -Unique)
    $lensFailure=$null
    throw ('Tunnel process exited; exit code '+$lensProcess.ExitCode+'; codes: '+($lensCodes -join ',')+'. Raw output suppressed.')
}
[pscustomobject]@{pid=$lensProcess.Id;startTicks=$lensStartTicks;url=$lensDomain;upstream='http://127.0.0.1:4318';localInspection=$false}|ConvertTo-Json|Set-Content -LiteralPath $lensReceipt -Encoding UTF8
Write-Output 'Tunnel process started. Public HTTPS and phone checks are still required.'
