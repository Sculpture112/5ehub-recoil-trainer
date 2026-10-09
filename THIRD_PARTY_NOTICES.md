# 第三方内容与许可范围

本仓库的 MIT 许可覆盖本项目原创的训练扩展和工具，不授予第三方地图、资源或参考内容的权利。

| 内容 | 来源与说明 |
| --- | --- |
| 5EHub 原地图、原脚本及地图框架 | [Steam 创意工坊 3086023598](https://steamcommunity.com/sharedfiles/filedetails/?id=3086023598)，权利属于原作者。本仓库不提交完整原地图源码或原地图数据卷；构建时从用户安装的地图读取。 |
| RecoilMaster 的轨迹参考与点模型、材质 | [Steam 创意工坊 3100869952](https://steamcommunity.com/sharedfiles/filedetails/?id=3100869952)，权利属于原作者。`data/reference/ak47-template.json` 是第三方轨迹参考，不属于本项目 MIT 授权范围；点模型、材质在本机构建时读取。 |
| Counter-Strike 2、Source 2 API 与 Workshop Tools | Valve；需要用户自行通过 Steam 安装，不随源码分发。 |
| Python 运行时 | Python Software Foundation；发布包中的许可原文见 [licenses/Python-LICENSE.txt](licenses/Python-LICENSE.txt)。 |
| PyInstaller 引导程序 | [PyInstaller 许可及分发例外](https://pyinstaller.org/en/stable/license.html)，构建时安装，不把它声明为本项目原创代码。 |
| Source 2 Viewer / ValveResourceFormat | [上游仓库](https://github.com/ValveResourceFormat/ValveResourceFormat)，仅作为用户自行安装的构建工具，不随源码分发。 |

发布页 ZIP 是指定历史补丁的原样存档，包含基于原地图编译的替换脚本及少量第三方资源。公开本项目源码并不等于这些第三方内容获得 MIT 许可，也不表示原作者或 Valve 对本项目作出认可。再次分发第三方内容须遵守原作者许可。
