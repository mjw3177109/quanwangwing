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
python3 tools/analyze_swf.py --phase assets --timeout 120
```

- `inventory`：运行 FFDec header、tag dump、AS1/AS2/AS3 清单、link report、ActionScript 导出。每条命令单独限时，失败保留已生成的报告和日志。
- `assets`：导出 image/shape/sound/font/text/binaryData/symbolClass，耗时较长；可在本地单独运行。
- `all`：同时执行以上两阶段。
- `build/swf-analysis/summary.json`：各步骤 exit code、耗时、超时状态、导出数量和完整性判定。
- `build/swf-analysis/exports/`：本地原版资源与脚本，不自动提交。

GitHub Actions 定时执行 `inventory`；原版素材和完整反编译脚本不上传公开仓库或公开 Actions artifact。公开的 CI artifact 仅包含 JSON 结构报告、命令日志与链接报告。遇到 FFDec 卡死，优先查看对应 `*.log` 和 `summary.json`，不得跳过失败宣称成功。

## 下一步

使用 `character_id`、`symbol_class`、`export_assets` 以及 FFDec 导出目录建立角色/动作/资源映射。招式帧数、判定盒、输入缓冲、伤害、硬直等必须由原版脚本/时间轴证据确定，不能用测试占位值冒充。
