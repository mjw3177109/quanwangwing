# M1 — 原版声音定义、触发与流式音频结构证据

从原始 SWF 的真实字节和 `swf-manifest.json` 建立声音元数据索引：`DefineSound` (14)、`StartSound` (15)、`DefineButtonSound` (17)、`SoundStreamHead/2` (18/45)、`SoundStreamBlock` (19)、`StartSound2` (89)。

```bash
python3 tools/build_sound_evidence.py --swf '拳皇wing1.4.swf' --manifest build/swf-analysis/swf-manifest.json --output build/swf-analysis/sound-evidence.json
```

先校验 SWF SHA-256，再逐条核对 tag header、offset、length。记录原始声音 ID、格式、采样率代码、采样数、时间轴、零基帧、流头和流块的结构关联；不复制音频字节或 SOUNDINFO envelope。无法关联本地 DefineSound 的引用和没有流头的块均明确列为未解析项。

**证据边界：** 时间轴 StartSound/按钮转换与音频真实可听时间不是同一概念。ActionScript 触发、外部资源、音频延迟、混音、循环点、音量、角色招式与 BGM 的最终关联仍未验收；不能用此索引冒充音频 1:1 还原。原始 SWF 和 FFDec 不修改，原始音频不公开分发。
