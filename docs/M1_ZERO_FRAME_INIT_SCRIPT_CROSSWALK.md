# M1：零 ShowFrame Sprite 与 DoInitAction 脚本入口交叉验证

使用 `tools/build_zero_frame_init_crosswalk.py` 对三份**同源 SWF SHA-256** 的结构证据执行只读连接：

```bash
python3 tools/build_zero_frame_init_crosswalk.py \
  --manifest build/swf-analysis/swf-manifest.json \
  --zero build/swf-analysis/zero-frame-sprite-references.json \
  --scripts build/swf-analysis/script-entry-evidence.json \
  --output build/swf-analysis/zero-frame-init-crosswalk.json
```

对每条零 ShowFrame Sprite 的静态 DoInitAction 引用，按**时间轴与原始解压偏移**匹配 script-entry，再与 manifest 中的真实 tag 59、目标 sprite ID、帧号和字节长度交叉校验。任一来源哈希、入口数量、目标、偏移或长度不一致则失败。仅输出数字元数据，不输出原始脚本、ExportAssets 名称、美术或音频。

2026-10-31 在 [main run 41142513521](https://github.com/mjw3177109/quanwangwing/actions/runs/41142513521) 的 `swf-analysis` artifact 上离线验证：175 个零 ShowFrame Sprite 全部没有内部非 End 标签；全部有 1 个 ExportAssets 名称，且分别有 1 条来自主时间轴第 1 帧（zero-based frame 0）的 DoInitAction 脚本入口，175 条均按偏移、目标和长度匹配。对应 tag body 长度合计 383,608 字节，单条最小 1,114 字节、最大 5,868 字节。这些数字来自该次 artifact，后续每次 CI 应重新计算，不应作为固定断言。

**证据边界：** 静态初始化链接不能证明脚本已在运行时执行，也不能证明 Sprite 可见、可选角色、动作、伤害或碰撞箱。脚本容器字节数不是 ActionScript 函数数量。零 ShowFrame Sprite 不应被补成假动画帧；原版资产仍与公开代码分离。
