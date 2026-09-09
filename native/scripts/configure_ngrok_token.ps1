# Interactive single-secret provisioning. No plaintext files or command-line token.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$lensRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$lensSecretDir = Join-Path $lensRoot 'runtime\ngrok-private'
[IO.Directory]::CreateDirectory($lensSecretDir) | Out-Null
$lensIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().User
$lensAcl = New-Object Security.AccessControl.DirectorySecurity
$lensAcl.SetOwner($lensIdentity)
$lensAcl.SetAccessRuleProtection($true, $false)
$lensRule = New-Object Security.AccessControl.FileSystemAccessRule($lensIdentity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$lensAcl.AddAccessRule($lensRule)
Set-Acl -LiteralPath $lensSecretDir -AclObject $lensAcl

$lensForm = New-Object Windows.Forms.Form
$lensForm.Text = 'ngrok - 本机密钥配置'
$lensForm.ClientSize = New-Object Drawing.Size(550,210)
$lensForm.StartPosition = 'CenterScreen'
$lensForm.FormBorderStyle = 'FixedDialog'
$lensForm.MaximizeBox = $false
$lensForm.ShowInTaskbar = $true
$lensForm.TopMost = $true
$lensForm.Add_Shown({
    $lensForm.WindowState = [Windows.Forms.FormWindowState]::Normal
    $lensForm.Activate()
    $lensBox.Focus()
    [IO.File]::WriteAllText((Join-Path $lensSecretDir 'dialog-state.json'),('{"shown":true,"pid":' + $PID + '}'),[Text.Encoding]::ASCII)
})
$lensForm.Font = New-Object Drawing.Font('Microsoft YaHei UI',10)
$lensLabel = New-Object Windows.Forms.Label
$lensLabel.Text = "从 ngrok 控制台复制 Your Authtoken，粘贴到下方。`n仅加密保存到当前 Windows 账号；不要发到聊天里。"
$lensLabel.Location = New-Object Drawing.Point(18,15)
$lensLabel.Size = New-Object Drawing.Size(510,55)
$lensForm.Controls.Add($lensLabel)
$lensBox = New-Object Windows.Forms.TextBox
$lensBox.Location = New-Object Drawing.Point(20,80)
$lensBox.Size = New-Object Drawing.Size(505,30)
$lensBox.UseSystemPasswordChar = $true
$lensForm.Controls.Add($lensBox)
$lensSave = New-Object Windows.Forms.Button
$lensSave.Text = '加密保存'
$lensSave.Location = New-Object Drawing.Point(395,135)
$lensSave.Size = New-Object Drawing.Size(130,38)
$lensForm.Controls.Add($lensSave)
$lensForm.AcceptButton = $lensSave
$lensSave.Add_Click({
    $lensPlain = $lensBox.Text.Trim()
    if ($lensPlain -notmatch '^[A-Za-z0-9_-]{20,200}$') {
        [Windows.Forms.MessageBox]::Show('请只粘贴 Authtoken，不要粘贴命令或整页文字。','格式检查') | Out-Null
        return
    }
    $lensSecure = $null
    try {
        $lensSecure = ConvertTo-SecureString -String $lensPlain -AsPlainText -Force
        $lensSealed = ConvertFrom-SecureString -SecureString $lensSecure
        [IO.File]::WriteAllText((Join-Path $lensSecretDir 'authtoken.dpapi'),$lensSealed,[Text.Encoding]::ASCII)
        [IO.File]::WriteAllText((Join-Path $lensSecretDir 'provisioned.json'),'{"credentialSaved":true,"protection":"Windows DPAPI current user","tunnelOnline":false}',[Text.Encoding]::ASCII)
        $lensBox.Clear()
        [Windows.Forms.MessageBox]::Show('已加密保存。后续连接由开发工具处理。','保存完成') | Out-Null
        $lensForm.Close()
    } catch {
        [Windows.Forms.MessageBox]::Show('保存失败；未输出密钥。请告知开发助手。','保存失败') | Out-Null
    } finally {
        $lensPlain = $null
        if ($null -ne $lensSecure) { $lensSecure.Dispose() }
    }
})
[void]$lensForm.ShowDialog()
$lensBox.Clear()
$lensForm.Dispose()
