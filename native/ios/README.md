# iPhone 原生工程 · v0.15

v0.15 统一清爽浅色与低饱和绿，主 App 分为人物/片段/候选三个步骤，建议扩展使用可滚动的长草稿预览。见 [视觉规范](../../02_product/MOBILE_UI_SYSTEM.md) 与 [UI 验收](../../07_reviews/V0_15_UI_ACCEPTANCE.md)。

主 App：Keychain 保存设备授权、HTTPS 配对、人物选择、批准片段分析、系统照片选择与明确批准 OCR、草稿编辑。建议键盘：只显示主 App 批准的最小草稿，核对人物后兑换一次短期授权并插入，不触发发送。

在 Mac 执行 `xcodegen generate --spec native/ios/project.yml --project native/ios`，打开生成的 Xcode 工程。GitHub Actions `macos-15` 选定 Xcode 26.3，并运行 Simulator 构建、核心测试及启动检查；实际运行状态以 CI 回执为准。

真机必须在两个 Target 配置同一个 Apple Developer Team 和 App Group。当前组名 `group.com.conversationlens.shared` 是工程默认值；个人账号需配置有效标识。模拟器无签名构建不等于真机签名或 App Store 审核通过。

键盘的系统“允许完全访问”默认由用户关闭。Apple 要求启用该能力后才能使用主 App 的共享容器。未启用时键盘不给出联网插入。启用后只在本人点击确认时向配对服务发送 30 秒、一次性的插入令牌；长期设备令牌仅在主 App Keychain，不共享给键盘，不上传按键、宿主文本或聊天全文。

服务端每次兑换重新检查设备撤销、人物、关系与修订，所以旧草稿不会因为被复制到共享容器而绕过撤销。共享文件使用完整文件保护并排除备份，读取过期或消费前删除；主 App 修改片段、人物、目标、模式或所选图片会作废旧授权。键盘展示后如果共享草稿被替换，必须刷新并重新确认。

中文完整输入继续使用熟悉的系统输入法，此扩展是建议插入键盘，不宣称已完成 iPhone 拼音引擎。iOS 无法可靠识别第三方 App 内聊天人物，始终需要本人确认；密码或拒绝第三方键盘的宿主由系统接管。

本轮先实现照片入口；系统分享扩展、真机三平台、无障碍字号与完整生命周期验收仍须补齐。主 App 与键盘均强制 HTTPS，不允许 ATS 全局绕过。真实服务部署和 Apple 签名不由模拟器替代。

官方依据：https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/CustomKeyboard.html
