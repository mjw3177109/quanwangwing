# 拳皇 Wing 1.4 — HTML5 重构工程

目标：以原始 SWF 为行为与资源参考，使用 HTML5 Canvas、JavaScript 和数据驱动的格斗运行时，逐项重建游戏。验收目标是可测量的高保真复刻；在完成原版资源、脚本和逐帧对照前，不把任何阶段称为 1:1 完成。

## 当前仓库

- 原始 SWF：根目录的 拳皇wing1.4.swf
- 反编译器：FFDec/ffdec.jar
- Java：分析脚本严格要求 Java 8（1.8）
- HTML5 工程：web/
- SWF 分析脚本：tools/analyze_swf.py
- 分析报告：GitHub Actions artifact，名称为 swf-analysis

## 本地运行

1. 安装 64 位 Java 8、Python 3.10+ 和 Node.js 20+。
2. 在仓库根目录运行：python tools/analyze_swf.py
3. 运行测试：npm --prefix web test
4. 启动预览：python -m http.server 8000 --directory web
5. 浏览器打开 http://localhost:8000

默认 `inventory` 仅生成真实 SWF 头、全部 tag/时间轴/角色 ID 清单及 FFDec tag dump；耗时较长的 AS1/AS2 诊断、ActionScript 源码和素材导出分别使用 `--phase deep`、`--phase scripts`、`--phase assets`。详见 `docs/SWF_INVENTORY.md`。不要覆盖原始 SWF。

## GitHub Actions

- push 到 main、手动触发或每小时第 17 分钟会执行 SWF 结构清点与 HTML5 单元测试；不代表完整 ActionScript 已还原。
- 导出结果作为 7 天保留期的 Actions artifact，不自动提交大体积导出资源。
- 自动任务失败时先修复根因，不以“任务启动”代替“分析成功”。

## 重构顺序

1. 完整解析 SWF：版本、舞台尺寸、帧率、时间轴、标签、脚本、符号映射、资源。
2. 建立角色与动作数据表：角色、招式、帧数、位移、碰撞箱、取消窗口、受击/击飞/倒地状态。
3. 建立 HTML5 渲染与音频层：精灵帧、时间轴、镜像、混合、音频同步。
4. 建立战斗运行时：固定帧时钟、输入缓冲、指令识别、命中判定、硬直、受击停顿、连段。
5. 重建菜单、角色选择、对战、胜负流程。
6. 与原版逐项对照，修复差异并形成可重复验收报告。

## 重要说明

当前 web/ 是引擎预览骨架，不是完整游戏。角色图、招式表和碰撞数据必须从 SWF 分析中确认后再导入，不能凭猜测填充。FFDec 本身按其随附许可证分发；原版游戏、角色、美术、音效等内容的权利需单独确认。导出的原版资源默认保留在本地/Actions artifact，不自动复制到公开仓库。
