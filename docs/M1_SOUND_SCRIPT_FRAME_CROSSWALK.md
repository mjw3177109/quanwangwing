# M1：原版 StartSound 与脚本容器同帧证据

在 SWF 字节级校验产生的 `swf-manifest.json`、`sound-evidence.json`、`script-entry-evidence.json` 基础上，按**相同时间轴 + 零基帧**关联每条 StartSound（Tag 15）与 DoAction/DoInitAction/DoABC 脚本容器（Tag 12/59/72/82）。先检查三个报告的源 SWF SHA-256 完全一致，再逐条与原始 tag 清单核对 timeline、frame、decompressed offset、tag code / sound ID。任何缺失或篡改均失败。

```bash
python3 tools/build_sound_script_crosswalk.py \
  --manifest build/swf-analysis/swf-manifest.json \
  --sound build/swf-analysis/sound-evidence.json \
  --scripts build/swf-analysis/script-entry-evidence.json \
  --output build/swf-analysis/sound-script-crosswalk.json
```

输出包含每个声音触发标签的原始位置、声音 ID、同帧脚本容器标签与相对字节顺序，以及声音 ID、时间轴统计。全部是元数据，不能据此认定哪个脚本触发音效。没有同帧脚本不意味着没有脚本或外部资源参与；同帧 DoInitAction 也不是已验证的战斗音效逻辑。后续必须通过 FFDec 脚本调用链与运行时播放行为验证招式音效、循环、音量及触发时刻。原始 SWF、FFDec、脚本正文和音频字节均不修改或公开导出。
