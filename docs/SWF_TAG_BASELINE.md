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

## 独立 SWF 解析交叉验证

来自 [run 40995595615](https://github.com/mjw3177109/quanwangwing/actions/runs/40995595615) 的 `swf-manifest.json`：

- 原始文件 SHA-256：`cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb`
- 格式：CWS，SWF version 9，解压后 22,878,991 字节
- **原始舞台：660 × 485 px；32 FPS；主时间轴 39 帧**
- 完整 tag 数：98,210（包含每个嵌套 Sprite 的 End tag）；与 FFDec 的 96,435 相差 1,775，恰好等于 Sprite 数量，说明 FFDec dump 省略了嵌套 End 记录
- Character 定义 14,562 条，AS1/AS2 脚本 tag 3,065 条，ExportAssets 名称 715 个
- 未发现 AS3 DoABC tag；不得运行无意义的 AS3 dump

根据 `ExportAssets` 中的 `__Packages.*_role` 名称，目前可**确认存在对应角色类**（但尚不能确认全部可选/隐藏角色规则）：Kyo、Mai、Iori、K、Kula、Ryo、Moriya、Orochi。每个名称均同时存在 `Type2_...` 变体类；具体游戏模式需从脚本确认。
