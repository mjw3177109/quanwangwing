# M1 — ShowFrame 与 End 之间的尾部标签证据

以 `swf-manifest.json` 和已交叉校验的 `frame-count-audit.json` 为输入，对帧数不一致的每条时间轴逐一检查最后一个 `ShowFrame` 与 `End` 之间的标签。分类为：无 `ShowFrame`、最后一帧后直接 `End`、或最后一帧后仍存在其他标签。报告记录标签代码、数量及解压偏移，不保存标签 payload。

```bash
python3 tools/build_frame_tail_evidence.py \
  --manifest build/swf-analysis/swf-manifest.json \
  --audit build/swf-analysis/frame-count-audit.json \
  --output build/swf-analysis/frame-tail-evidence.json
```

校验 SHA-256、全部时间轴声明、逐时间轴标签顺序与帧号、唯一 End、原始 ShowFrame 数量和审计差异行，异常时拒绝生成报告。该分析不会擅自补帧，也不能仅凭尾部标签判断原版 SWF 是否损坏。必须继续通过 FFDec 时间轴及原版实际播放验证。仅将 metadata 放入 Actions artifact，原版 SWF、反编译脚本、美术和音频保持隔离。
