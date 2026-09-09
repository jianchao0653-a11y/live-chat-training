# MADR-046：截图逐条校对与未完成验收的继续推进

- 日期：2026-09-09
- 状态：IMPLEMENTED（v0.17.2测试版）
- 承接：MADR-044、045，用户要求继续完成未完成内容。

## 决策

本机OCR识别后增加逐条校对对话框。保留原始识别文字，每条可编辑并选择“我／对方／不纳入”；几何位置的推测不自动确认。未选择发言人、保留空条目、全部排除、超过4000字都不回填；最多80条，超限要求缩小截图范围。多行内容逐行附上同一确认发言人。

用户确认后回填聊天片段，但不自动批准分析、不自动发送。取消保留原始待核对文字；输入现场过期后拒绝回填。对话框沿用现有视觉字段样式和FLAG_SECURE；校对内容只在当前进程中，未新增云端上传、存储或依赖。

本轮不以硬编码替换“明夭”等错字提高评测分数，也不把繁简转换当作逐字识别通过。原OCR精确质量22/30缺口继续记录。先让使用者能可靠校正，再用经授权的实际截图扩大质量评测。

## 已阅读证据与适用性

- [ML Kit Android文字识别](https://developers.google.com/ml-kit/vision/text-recognition/v2/android)，2026-09-09：字符像素、清晰度影响准确率，通常超过24×24像素没有额外精度收益。已有合成字体32–44px，不能假设简单放大会解决错字。采纳人工校对和保留原文，不更换识别引擎。
- [ngrok Traffic Inspector](https://ngrok.com/docs/obs/traffic-inspection)，2026-09-09：默认存请求/响应元数据，Full Capture为账户主动开启，可存头和正文，免费账户保留24小时。文档默认值不等于已核验当前账户；仍需账户设置证明Full Capture关闭，现有inspect=false也不能代替它。
- [GitHub Actions计费说明](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)，2026-09-09：私有仓库运行涉及包含额度及预算。无runner、无steps不足以确定是计费故障，不能代用户购买或自行声称原因。已请求用户提供失败Summary具体文字；不盲目重跑。

## 工具问题与验证

浏览器连接工具启动失败：沙箱helper程序未找到，无法读取用户已登录GitHub/ngrok页面。没有修改安全配置；另用独立Playwright CLI补验本机合成网页。CLI不属于产品运行依赖，缓存仅在runtime中。第一次npx帮助命令结束时出现UV_HANDLE_CLOSING；后续正常网页命令成功，未将该工具退出异常当作产品问题。

Android仪器入口首次未注册；改为既有OcrTestRunner的review参数运行。第一次测试在OnShow回调前触发按钮，断言失败；补充主线程空闲同步后验证实际控件行为，未修改业务判断来迎合测试。

后端71/71；原生策略、图像边界及新增OCR校对纯Java检查通过；Android校对界面、云端合成闭环、原签名升级和真实预算内合成链路通过。详细交付及仍需真人/账户侧完成的事项见 `07_reviews/V0_17_2_CONTINUATION.md`。
