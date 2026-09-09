# 待提交厂商的安全核实材料

状态：仅草稿，未发送、未上传样本。报告不包含账户、Authtoken、业务域名、聊天数据或本机个人路径。

Subject: Please verify Windows ngrok archive flagged by Microsoft Defender

On 2026-09-08, an archive downloaded from the link provided on https://ngrok.com/download/windows was quarantined by Microsoft Defender after extraction. The executable did not successfully run; its Authenticode signature could not be verified before quarantine.

- Download URL: https://bin.ngrok.com/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip
- ZIP size: 12257844 bytes
- ZIP SHA256: 699bbf1932ec43a573b764bd03e6568efa2c4e45955eb3cc2089c19bb4be4464
- Subsequent read-only verification: this ZIP hash matches the official archive entry for version 3.39.11 Windows amd64 at https://dl.equinox.io/ngrok/ngrok-v3/stable/archive (checked 2026-09-08). This does not establish that the detection is a false positive.
- Detected extracted filename: ngrok.exe
- Detection: Trojan:Win32/Kepavll!rfn
- Defender engine: 1.1.26080.3
- Security intelligence: 1.459.103.0
- Defender events: 1116 (detection), 1117 (quarantine successful)

Follow-up on 2026-09-08: Microsoft Update-MpSignature completed and security intelligence advanced to 1.459.107.0, with antivirus and real-time protection enabled. A targeted Start-MpScan of the already hash-verified ZIP completed (events 1000/1001). Events 1116/1117 again detected Trojan:Win32/Kepavll!rfn inside the ZIP and successfully quarantined the archive. No re-extraction, execution, exclusions, or quarantine restoration was performed. Updating security intelligence did not resolve the detection.

Please confirm whether this exact archive hash matches an official release and investigate this detection with the security vendor. Please provide verifiable release integrity/signing information and a remediation path that preserves antivirus protection. We have not classified this as a false positive, restored the file, or added an exclusion.

参考：https://ngrok.com/docs/faq 。正式发送或提交样本需要用户明确授权；本草稿不代表已联系厂商或已获回复。
