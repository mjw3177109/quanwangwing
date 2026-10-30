# M1 — 原版时间轴帧数差异取证

上一轮在原始 SWF 的 1,776 条时间轴中发现 175 条声明帧数与 ShowFrame 标签数不一致。此工具对原始结构 manifest 和已校验的 display-depth-evidence 进行交叉核验，按 **少于声明帧数 / 多于声明帧数** 分类，输出每个异常时间轴的 ID、差值、最后一帧与 End 标签的解压偏移，以及脚本和显示列表标签数量。

```bash
python3 tools/build_frame_count_audit.py \
  --manifest build/swf-analysis/swf-manifest.json \
  --depth build/swf-analysis/display-depth-evidence.json \
  --output build/swf-analysis/frame-count-audit.json
```

校验包括 SWF SHA-256、全部时间轴集合、逐帧 ShowFrame 偏移和顺序、声明帧数、汇总数量。任一不一致直接失败，不根据猜测修正帧数。输出仅包含可追溯的标签元数据；不包含原始 SWF、AS2、图像或音频正文。

**证据边界：** 帧数差异并不自动意味着 SWF 损坏，也不能据此判断动画实际时长、角色招式、碰撞箱或渲染是否正确。需要结合 FFDec 的时间轴视图、原版运行录屏与嵌套 Sprite/ActionScript 进一步排查。不要把这份静态索引当作 1:1 复刻证明。
