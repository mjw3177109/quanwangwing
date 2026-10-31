# M1 — 零 ShowFrame Sprite 的静态引用交叉索引

本轮修复了一个覆盖缺口：原版 SWF 有 **192 个零 ShowFrame Sprite**，其中 175 个声明 1 帧（因此出现在帧数差异报告中），另有 17 个声明 0 帧（因此不属于帧数差异）。旧实现仅遍历 175 条差异记录，会漏掉后者。新实现以原始 `DefineSprite` 定义及各 Sprite 的真实 `ShowFrame` 标签为全集，同时独立核验 `frame-tail-evidence.json` 的差异行，避免将「无差异」误当成「不存在」。

工具逐个核对 characterId、内部标签代码、静态 PlaceObject/2/3 引用、DoInitAction 目标、ExportAssets 和 SymbolClass 名称数量。`zero_sprite_declared_frame_counts` 和两类覆盖计数用于后续 Actions 门禁。192/175/17 是 2026-10-31 的原版 SWF artifact 已观察到的结构数量，不是对未来文件的硬编码假设。

```bash
python3 tools/build_zero_frame_sprite_references.py \
  --manifest build/swf-analysis/swf-manifest.json \
  --tail build/swf-analysis/frame-tail-evidence.json \
  --output build/swf-analysis/zero-frame-sprite-references.json
```

输出包括原始 SWF SHA-256、定义标签偏移、静态引用所在时间轴/帧/标签偏移、资源名称数量与分类汇总；不包含名称正文、原版 SWF、ActionScript、图像或音频。检查 SHA、声明与时间轴集合、差异行成员、原始 ShowFrame 数量、分类和引用字段；不一致则失败。仅发布 metadata artifact。

**证据边界：** 静态引用不代表实际渲染、可达性或角色动作。没有静态引用也不能证明 Sprite 未被使用：`attachMovie`、外部资源加载与 ActionScript 动态路径尚未解析。零 ShowFrame 不应被自动补成一帧，也不能据此断言 SWF 损坏。下一步结合 FFDec 视图、AS2 角色创建链和运行时逐帧对照。
