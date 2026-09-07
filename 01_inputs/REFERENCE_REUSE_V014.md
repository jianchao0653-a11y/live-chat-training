# v0.14 实际复用清单

更新：2026-09-07。区分运行依赖、工程工具、方法参考与候选，不能把参考库算作已经集成。

| 项目 | 实际使用 | 证据与边界 |
|---|---|---|
| [rime/librime](https://github.com/rime/librime) 1.17.0 | Android 中文输入引擎，真实 JNI 调用 | BSD-3-Clause；`native/dependencies.lock.json` 锁 commit/校验；自写 Android/JNI 界面 |
| [rime/rime-pinyin-simp](https://github.com/rime/rime-pinyin-simp) | 简体拼音词库 | Apache-2.0；与 librime 一起构建，不启用用户学习 |
| Boost、yaml-cpp、LevelDB、marisa-trie、OpenCC | 上述引擎实际编译依赖 | 完整版本/许可见 lock 与构建产物 THIRD_PARTY_NOTICES；不能遗漏传递依赖 |
| [ReactiveCircus/android-emulator-runner](https://github.com/ReactiveCircus/android-emulator-runner) | GitHub Ubuntu KVM 启动官方 Android Emulator | action 固定 commit；API 34/36 合成验收；模拟器本体来自 Android SDK |
| [android-actions/setup-android](https://github.com/android-actions/setup-android) | 安装云端 Android SDK 工具入口 | action 固定 commit；修复首次 sdkmanager 不在 PATH 的失败 |
| [actions/runner-images](https://github.com/actions/runner-images) | GitHub Ubuntu/macOS 构建环境及版本清单 | macOS 15 + Xcode 26.3；iOS Simulator 来自 Apple Xcode，不是该仓库实现的 iPhone 模拟器 |
| [yonaskolb/XcodeGen](https://github.com/yonaskolb/XcodeGen) | 从 project.yml 生成 iOS App/键盘/测试工程 | MIT；CI 输出安装版本，当前 brew 版本尚未锁死 |
| Node.js HTTP/SQLite、OpenAI Responses | 本地业务服务、存储与模型接口 | 不额外接入 Graphiti/Mem0 服务；模型维持 GPT + 逻辑 6+2 与独立终审 |

## 借鉴方法，未复制实现

- [Graphiti](https://github.com/getzep/graphiti)：关系记忆的时间、证据与可修正性；本项目实际由 SQLite 的 pair、事件、修订和作废机制实现。
- [Mem0](https://github.com/mem0ai/mem0)：记忆检索、更新与遗忘问题分解；未安装 Mem0 运行服务。
- [ConvoKit](https://github.com/CornellNLP/ConvoKit)：明确说话人与会话分析；本项目不把未知说话人硬推断为对方。
- [xiaolai/bureau](https://github.com/xiaolai/bureau)、[nlpm](https://github.com/xiaolai/nlpm)、[xros](https://github.com/xiaolai/xros)、[eou-foundry](https://github.com/xiaolai/eou-foundry)、[vmark](https://github.com/xiaolai/vmark)：来源→决策→实现→验证、Markdown 治理与不凭空声明完成。未复制其代理、Schema 或治理代码。

## 仍是候选或研究池

FlorisBoard、HeliBoard、Trime 前端未复制或 fork；尤其不能将 Trime 的 GPL 前端与 librime 的 BSD 引擎混为一谈。Letta、LangMem 是记忆架构参考；PaddleOCR、Tesseract.js、OmniParser、MiniCPM-V 尚未集成。当前 OCR 实际走支持图片的 GPT 接口，尚无真实质量验收。

CPED、MPDD、SocialDial、FANToM、ToMBench、CEI、RECCON、SOTOPIA、ToMAP 等是评估研究池，没有把数据集导入产品。Ex-AI、Orbit、RelateAI、whatsapp-llm、ALSO、MapDia 等名称尚未完成仓库身份/许可核验，不能宣称采用。

研究来源与更早处理记录保留在 `REFERENCE_PROJECTS.md`、`NEEDS_TXT_IMPLEMENTATION.md`。真正新增第三方代码时须重新核对当前许可证，并保留通知。

云端调试还查阅了 [AOSP Android 14 InputMethodManagerService](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-14.0.0_r1/services/core/java/com/android/server/inputmethod/InputMethodManagerService.java)：其 help/handler 明确 `ime list` 默认仅显示已启用输入法，`-a` 才列全部。用于修正测试脚本语义，没有复制系统服务实现。
## v0.15 UI 补充

视觉原则参考 Material 3 的颜色角色/字体层级、Apple HIG 的原生控件与动态字体、WCAG 的文字对比度方法；实现为自有 LensStyle/LensTheme token，无新增第三方 UI 运行依赖，没有复制其他输入法前端。具体链接、颜色与约束见 [视觉规范 1.0](../02_product/MOBILE_UI_SYSTEM.md)。上文保留 v0.14 工程复用账本。
