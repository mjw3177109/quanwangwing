# 拳皇 Wing 1.4 — 首轮 FFDec Tag 基线（2026-10-30）

来源：GitHub Actions run [40992376818](https://github.com/mjw3177109/quanwangwing/actions/runs/40992376818) 的 `swf-tags.txt`（artifact 12950799219）。该 run 因新版分析脚本提交而取消，不能视为完整解析成功；但已输出的 tag dump 可独立核查。

| SWF Tag | Code | 数量 |
|---|---:|---:|
| ShowFrame | 1 | 38,322 |
| PlaceObject2 | 26 | 26,565 |
| RemoveObject2 | 28 | 6,442 |
| DefineShape | 2 | 5,853 |
| DefineBitsLossless2 | 36 | 5,376 |
| DoAction | 12 | 2,737 |
| **Unknown（自定义/未知）** | **253** | **2,729** |
| DefineSprite | 39 | 1,775 |
| SoundStreamHead2 | 45 | 1,551 |
| FrameLabel | 43 | 1,331 |
| StartSound | 15 | 816 |
| ExportAssets | 56 | 715 |
| DefineText | 11 | 460 |
| DoInitAction | 59 | 328 |
| DefineSound | 14 | 301 |
| Unknown | 255 | 1 |

总 tag 记录数：**96,435**（包括嵌套 Sprite 时间轴）。AS1/AS2 相关脚本 tag 合计 **3,065**，此数字仅为 tag 数，不等于独立函数数量。dump 中未观察到 DoABC/AS3 tag。Unknown tag 253/255 不属于普通标准资源，需保留原始偏移和 payload 证据，不能推断其用途。

**已确认的工具兼容性问题：** 当前仓库随附的 FFDec 不支持 `-header` 命令，也不接受 `-dumpAS2 -exportNames`。原脚本曾把命令行帮助当作 header 成功，并收到 `I/O error during reading`；AS3 dump 超时。后续使用纯 Python SWF 结构解析作为独立事实来源，并按随附 FFDec 实际帮助修正参数。完整 ActionScript 源码尚未导出和验证。

本文件只是原始 SWF 结构基线，**不表示 HTML5 1:1 复刻已完成**。
