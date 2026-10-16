# 构建与测试 adaptive 版本

## 源码入口

| 文件 | 用途 |
| --- | --- |
| `src/extension.js` | 发布包中训练扩展的逐字节副本，当前构建的权威输入 |
| `data/adaptive-recipe.json` | 两版原图的唯一上下文接入规则、所需接口和已验证场景摘要 |
| `tools/5ehub_adaptive.py` | 本机校验、兼容性检查、生成补丁与适配记录 |
| `tools/patch_5ehub_workshop_package.py` | VPK 读写及完整性校验；旧固定版本构建入口不是本版构建入口 |
| `tools/5ehub_view_bridge.py` | 控制台视角、屏幕晃动同步与训练会话退出保护 |
| `tools/fivehub_native_punch.py` | 仅双枪使用的控制台后坐力数据解析 |
| `installer/` | 与发布包一致的 Windows 安装、还原、诊断、启动脚本 |
| `src/diagnostics/`、`data/calibration/` | 扩展组件及测量数据，供维护与测试；不运行旧生成器拼接扩展 |

本版直接编辑编译资源的脚本 DATA 区，再重算资源及 VPK 校验，无需地图编辑器或反编译器。短上下文接入规则包含原地图代码片段，不在 MIT 授权范围。仓库不存放完整原地图脚本和原地图数据卷。

## Windows 本机构建

安装 Python 3.13。在仓库目录执行：

```powershell
python -m pip install -r requirements-build.txt
python tools/verify_snapshot.py
python tools/verify_snapshot.py --zip "D:\downloads\5EHub-Recoil-Patch.zip"
python tools/build.py --base-package "D:\downloads\5EHub-Recoil-Patch.zip"
```

`--base-package` 必须是本标签发布的原始 adaptive ZIP。它提供不纳入本仓库 MIT 授权的已编译点模型、材质、原图索引参考和回退 VPK；构建器先核验 ZIP，然后从本仓库源码重新编译两个 EXE，更新扩展、规则、安装脚本与清单摘要。原 EXE 会被新构建替换，不是复制改名。

产物位于 `dist/2026.10.16-integrated-12-adaptive-source-build.zip`。本构建只在仓库内写入，不安装或改写用户地图；安装另行运行产物的一键安装。PyInstaller 的构建时间和环境可能影响 EXE 字节，因此不承诺新产物与官方 ZIP 的 SHA-256 相同。

`verify_snapshot.py --zip` 比较两个主程序的可执行字节码、常量和异常表，忽略源码路径及行号；该检查须使用 Python 3.13。附属模块及 VPK 工具另外记录源文件摘要。源码修改后，需要重新评估规则、扩展、回退载荷和核验记录，不能只更新摘要冒充旧包对应源码。

## 不连接游戏的测试

```powershell
python tools/verify_5ehub_helper_lifecycle.py
python tools/verify_5ehub_native_punch.py
node tools/verify_preferences.cjs
node tools/verify_bot_invincible.cjs
node tools/verify_weapon_cue_isolation.cjs
node --check src/extension.js
```

前两个 Python 测试使用控制台替身，不启动游戏；完整安装测试需要 Windows PowerShell 5.1。Node 只用于开发测试，不是安装包依赖。

完整 VPK 测试需要作者合法取得的两份本机原图，不随源码发布：

```powershell
$env:FIVEHUB_FIXTURES_ROOT = "D:\local-fixtures"
$env:FIVEHUB_PACKAGE_ROOT = "D:\unpacked-adaptive-release"
New-Item -ItemType Directory -Force build
python tools/verify_5ehub_adaptive.py
python tools/verify_5ehub_adaptive_portable.py
```

原图固定目录为 `<FIVEHUB_FIXTURES_ROOT>/build/5ehub-20261009/workshop-mirror/3086023598` 和 `5ehub-20261013/...`。识别已知旧补丁的测试还需要 `<FIVEHUB_FIXTURES_ROOT>/dist/5EHub-Recoil-Patch-20261016-map-update/payload`。测试只在仓库 `build/` 创建沙盒，阻止调用真实 CS2 进程，不安装进实际 Steam 库。

发布前已通过：两版原图安装/重复安装/还原、兼容更新、损坏和接口变动拒绝、原有 002 卷保护、失败回滚、未知场景拒绝、更新后的原图还原；便携 EXE 的安装/检查/还原和启动自动重装；本机四武器两版绘制切换与屏幕晃动实际参数同步。实机效果仍受游戏更新影响。
