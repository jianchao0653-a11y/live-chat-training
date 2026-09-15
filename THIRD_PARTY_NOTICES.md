# Third-party notices

Conversation Lens downloads pinned source archives during the Android build and resolves locked Android dependencies through Gradle. Each dependency remains under its own license or service terms.

| Component | Pinned version | License / terms | Source |
|---|---:|---|---|
| librime | 1.17.0 | BSD-3-Clause | <https://github.com/rime/librime> |
| LevelDB | 1.23 | BSD-3-Clause | <https://github.com/google/leveldb> |
| yaml-cpp | 0.8.0 | MIT | <https://github.com/jbeder/yaml-cpp> |
| marisa-trie | 0.3.1 | BSD-2-Clause option selected | <https://github.com/s-yata/marisa-trie> |
| OpenCC | 1.1.9 | Apache-2.0 | <https://github.com/BYVoid/OpenCC> |
| Rime pinyin-simp dictionary | pinned commit | Apache-2.0 | <https://github.com/rime/rime-pinyin-simp> |
| Boost | 1.85.0 | Boost Software License 1.0 | <https://www.boost.org/> |
| Darts-clone, utf8cpp, X11 keysyms, RapidJSON | bundled upstream copies | See copied notices | Dependency source trees |
| Google ML Kit Chinese text recognition | 16.0.1 | [Google ML Kit terms](https://developers.google.com/ml-kit/terms) | Google Maven |
| AndroidX, Google Play services and Android build dependencies | locked in Gradle files | Their published licenses and terms | Google Maven / Maven Central |
| Android NDK libc++ runtime | NDK 28.2.13676358 | Apache-2.0 with LLVM exceptions and bundled NDK notices | Android NDK |

Exact commits and archive hashes are in [`native/dependencies.lock.json`](native/dependencies.lock.json). Copied license texts are under [`third_party/licenses`](third_party/licenses). The Android packaging script also generates `THIRD_PARTY_NOTICES.txt` and `NDK-NOTICES.txt` from the exact source and toolchain used for each build.

No Trime frontend source is included.

