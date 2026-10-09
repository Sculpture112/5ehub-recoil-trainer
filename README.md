# 5EHub Recoil Trainer

为 CS2 的 **5EHub 闪身训练**加入跟随移动 Bot 的压枪轨迹提示。通过红色轨迹和绿色当前提示点练习跟枪、压枪，并在双 Tab 菜单中调整训练选项。

这是安装到原版 5EHub 的本机训练补丁，需要先订阅原地图。

## 视频教程

**下面是安装、练枪方法及相关原理介绍的视频教程：**

[▶ CS2最强练枪图的安装，和练枪的一些介绍和解释，学会之后解锁donk同款激光枪](https://www.bilibili.com/video/BV1PBp46rEYw/)

## 下载与安装

1. 在 Steam 订阅并下载 [原版 5EHub](https://steamcommunity.com/sharedfiles/filedetails/?id=3086023598)。
2. 从 [Releases 下载补丁 ZIP](https://github.com/Sculpture112/5ehub-recoil-trainer/releases/latest)。请下载 `5EHub-Recoil-Patch.zip`，GitHub 自动生成的 Source code ZIP 是源码。
3. 退出 CS2，将补丁完整解压到普通文件夹。
4. 双击 **一键安装.cmd**；装过旧补丁也请保留原图备份目录。
5. 双击 **启动训练.cmd**。进入闪身模式，踩原地图按钮开始一轮；双击 Tab 打开设置菜单。

使用发布包无需安装 Python、Node 或 Workshop Tools，也不需要订阅 RecoilMaster。需要还原时，退出游戏后运行 **一键还原.cmd**。

## 功能

- 压枪轨迹跟随 Bot；经过的轨迹点消失，停火后绿色提示点回到起点。
- 两种绘制方式：第一版使用历史屏幕投影，第二版使用引擎投影的三维轨迹。
- 显示时机可选：持续显示、开火后显示、看见 Bot 时显示。
- 支持头部、脖子、身体目标，以及默认关闭的本地自瞄测试开关。
- 子弹时间、屏幕晃动、轨迹总开关与武器选择可在地图菜单中调整。
- 14 把武器、16 套轨迹；AUG、SG 553 的开镜与不开镜分别适配。
- 安装前检查地图版本、文件校验、旧备份、占用与权限，并提供分类错误提示。

支持武器：AK-47、M4A1-S、M4A4、Galil AR、FAMAS、AUG、SG 553、MAC-10、MP9、MP7、MP5-SD、UMP-45、P90、PP-Bizon。CZ75 未适配；M4A1-S 使用消音器，FAMAS 使用全自动。

## 本次公开的版本

初始公开版本固定对应 **2026.10.10-integrated-6**，即指定的历史 `5EHub-Recoil-Patch.zip`，适配 2026-10-09 版原地图。发布附件保持原 ZIP 字节不变。

```text
SHA-256
0f1d3c886c616487973f85550240def2cc9a593cb3001ce036b85f8eee6c7d6a
```

地图源码已与 ZIP 中的编译脚本核对；辅助程序的主要字节码已与源码核对，比较时忽略源码路径及行号。证据见 [release/source-verification.json](release/source-verification.json)。**本版本没有加入后续未发布的地图退出保护修改。**

## 辅助程序与使用范围

`5EHubAssist.exe` 的完整项目源码位于 [tools/5ehub_view_bridge.py](tools/5ehub_view_bridge.py)。它连接游戏原生的本机控制台接口，读取控制台返回的视角数据，并同步绿色提示点校正和屏幕晃动设置；源码没有游戏内存读取、内存写入、DLL 注入或驱动加载实现。

**此历史版本只在游戏控制台断开后退出，离开训练地图不保证退出。**训练结束后请完全关闭 CS2，确认辅助程序已结束，再从 Steam 正常启动游戏。启动器会为新启动的训练游戏添加 `-insecure`；本版本连接已有游戏时只检查控制台端口，尚未严格检查 `-insecure`。

项目用于本机训练。没有 Valve、5E 或其他平台的反作弊认证，也不能承诺“不会触发任何反作弊”。历史 ZIP 中同名空 TXT 是原包内容，文件名不是安全保证。

## 源码与构建

| 路径 | 内容 |
| --- | --- |
| `src/diagnostics/` | 轨迹绘制、训练菜单、子弹时间及校准脚本 |
| `data/calibration/` | 各武器的后坐力与显示校准数据 |
| `tools/5ehub_view_bridge.py` | 发布包辅助 EXE 对应的源码 |
| `installer/` | 从指定 ZIP 原样提取的安装、还原、启动脚本 |
| `tools/build.py` | 从本机原地图生成脚本、编译并打包 |
| `release/` | 历史发布清单和源码一致性记录 |

构建需要 Windows、Python 3.13、CS2 Workshop Tools、Source 2 Viewer CLI，以及本机安装的对应版本 5EHub 和 RecoilMaster。完整步骤见 [构建说明](docs/BUILD.md)。原地图完整源码、地图数据卷、账号信息和本机运行日志不提交到此仓库。

## 已知限制

第一版绘制需要选择与游戏一致的分辨率，部分电脑可能仍有错位。正常速度下绿色点可能存在轻微延迟或跳动。轨迹提示不能保证随机散布、停火续射或任意设置下的子弹逐发落在同一点。地图更新后如校验不匹配，请使用匹配版本的补丁，不要绕过校验。

## 许可与致谢

项目原创扩展和工具使用 [MIT 许可](LICENSE)。5EHub 原地图、RecoilMaster 参考与资源、Valve 内容及第三方运行时保留各自权利，见 [第三方说明](THIRD_PARTY_NOTICES.md)。
