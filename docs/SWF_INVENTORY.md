# SWF 结构清点与 FFDec 导出（M1）

原始文件：`拳皇wing1.4.swf`。**禁止覆盖原始文件。**

## 先取得可复核的原始结构数据

```bash
python3 -m unittest discover -s tests -v
python3 tools/swf_inventory.py --output build/swf-analysis/swf-manifest.json
```

`swf-manifest.json` 是不依赖 Java 的只读解析结果，包含：SWF signature、SHA-256、舞台 RECT、尺寸、帧率、帧数、所有 tag 的解压后偏移与长度、DefineSprite 子时间轴、脚本 tag 位置、characterId、SymbolClass 和 ExportAssets 名称。CWS 自动解压；ZWS 目前明确拒绝，不能假称已解析。它不等同于完整 ActionScript 语义或视觉还原。

## FFDec（Java 1.8）分阶段执行

```bash
java -version  # 必须是 1.8
python3 tools/analyze_swf.py --phase inventory --timeout 90
python3 tools/analyze_swf.py --phase deep --timeout 120
python3 tools/analyze_swf.py --phase scripts --timeout 120
python3 tools/analyze_swf.py --phase assets --timeout 120
```

- `inventory`：运行 FFDec tag dump 与纯 Python 完整结构清单（CI 必需检查）。每条命令单独限时，失败保留已生成的报告和日志。
- `deep`：运行 FFDec AS1/AS2/AS3 脚本清单和 link report。已观察到 FFDec 18.0.0 对此 SWF 的 `-dumpAS2` 和 `-linkReport` 可能各超时 90 秒；作为单独诊断，不能宣称完成。
- `scripts`：导出 ActionScript 近似源码，可能耗时较长；可在本地单独运行。
- `assets`：导出 image/shape/sound/font/text/binaryData/symbolClass，耗时较长；可在本地单独运行。
- `all`：同时执行以上四个阶段。
- `build/swf-analysis/summary.json`：各步骤 exit code、耗时、超时状态、导出数量和完整性判定。
- `build/swf-analysis/exports/`：本地原版资源与脚本，不自动提交。

GitHub Actions 定时执行 `inventory`；原版素材和完整反编译脚本不上传公开仓库或公开 Actions artifact。公开的 CI artifact 仅包含 JSON 结构报告、命令日志与链接报告。遇到 FFDec 卡死，优先查看对应 `*.log` 和 `summary.json`，不得跳过失败宣称成功。

## 下一步

使用 `character_id`、`symbol_class`、`export_assets` 以及 FFDec 导出目录建立角色/动作/资源映射。招式帧数、判定盒、输入缓冲、伤害、硬直等必须由原版脚本/时间轴证据确定，不能用测试占位值冒充。

## 已确认的旧版 FFDec 差异（2026-10-30）

仓库内 FFDec 的命令行帮助不包含 `-header`，并且 `-dumpAS2` 只接受 `<infile>`，不支持新版 `-exportNames`。旧版流水线误将帮助文本当作 header 成功、将 `I/O error during reading` 当作成功，并在不需要的 AS3 dump 中超时。新脚本改为使用纯 Python 读取真实 SWF header、去掉不兼容参数，并检查日志错误文本。原始 FFDec tag dump 含大量 253 自定义/未知 tag，不能把它们视为已解码的游戏逻辑。

**M1 尚未完成：** 2026-10-30 的 GitHub Actions run 40996027860 已确认结构解析与 FFDec tag dump 成功，但 `-dumpAS2` 和 `-linkReport` 分别在 90 秒超时，原版脚本语义仍需进一步提取。CI 的 `inventory` 成功仅代表结构清点通过，不能代表完整反编译成功。`scripts` 阶段提供独立的 ActionScript 源码导出路线。
