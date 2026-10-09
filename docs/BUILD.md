# 从源码构建 integrated-6

本说明生成指定 ZIP 对应的训练逻辑，不会安装补丁或启动游戏。重新构建的 EXE、VPK 和 ZIP 可能因编译器版本、路径及压缩元数据而具有不同摘要；历史发布附件仍是原始 ZIP。

## 环境

- Windows、Python 3.13。
- CS2 与 Counter-Strike Workshop Tools，需有 `game/bin/win64/resourcecompiler.exe`。
- [Source 2 Viewer CLI](https://github.com/ValveResourceFormat/ValveResourceFormat/releases)。
- 本机下载的 2026-10-09 版 5EHub（3086023598），以及 RecoilMaster（3100869952）。
- 地图文件必须匹配 `release/manifest.json`；较新地图不能直接套用旧脚本。

```powershell
py -3.13 -m pip install -r requirements-build.txt
```

## 构建

以下三个路径按本机安装位置替换：游戏目录、Steam 的 `workshop/content/730` 目录和 Source 2 Viewer 程序。

```powershell
py -3.13 tools/build.py --game-root "D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive" --workshop-root "D:\SteamLibrary\steamapps\workshop\content\730" --source2viewer "D:\Tools\Source2Viewer-CLI.exe"
```

输出：`dist/5EHub-Recoil-Patch.zip`。

构建器读取原地图或原图备份，检查数据卷摘要，提取原脚本、叠加本项目扩展，在独立的 `codex_5ehub_oss_integrated6` addon 中编译，再生成增量 VPK 和辅助 EXE。它不会覆盖订阅地图；安装需另外运行产物中的“一键安装.cmd”。

如果已安装补丁，必须保留地图目录中的 `.aim-recoil-patch-backup`，构建器从其中读取原版目录卷。只有编译需要 RecoilMaster 资源；最终用户安装发布包不需要订阅它。

可追加 `--stage source` 仅生成并核对脚本，`--stage map` 生成地图增量文件，`--stage helper` 仅生成 EXE。完整构建使用默认 `--stage all`。

## 核对历史附件

```powershell
py -3.13 tools/verify_snapshot.py --zip "D:\Downloads\5EHub-Recoil-Patch.zip"
```

验证器检查指定 ZIP 摘要、发布清单、安装脚本逐字节对应及辅助主程序字节码对应。地图源码一致性记录位于 `release/source-verification.json`；构建器会再次检查生成源码摘要。
