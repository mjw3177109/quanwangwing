# M1：零 ShowFrame Sprite 与 FFDec AS2 类路径交叉证据

本增量在 **FFDec 导出通过完整性检查后**，将原版 SWF 的 `ExportAssets` 名称、零 `ShowFrame` 的 `DefineSprite` ID 与导出的 AS2 文件索引交叉核对。

```bash
python3 tools/build_zero_frame_as2_class_links.py \
  --manifest build/as2-probe/swf-manifest.json \
  --asset-index build/as2-probe/asset-index.json \
  --export-index build/as2-probe/script-export-index.json \
  --output build/as2-probe/zero-frame-as2-class-links.json
```

仅对形如 `__Packages.Foo.Bar` 的 ExportAssets 名称推导候选 `scripts/__Packages/Foo/Bar.as` 路径。若该路径确实存在于**已经校验过文件数量、字节长度及 SHA-256 的 FFDec 导出索引**，标记 `verified_path_match`；不符合路径规则的标记 `not_class_path`，符合规则但找不到文件的标记 `unmatched_class_path`。不能因没有找到匹配就编造类或动作数据。

输出仅包含原始 `characterId`、定义偏移、初始化目标计数、SHA-256、长度和分类计数；不包含 ExportAssets 名称明文、AS2 文件路径明文、ActionScript 正文、图像或声音。来源哈希、定义偏移、导出清单和文件索引不一致时必须失败。真实匹配数量由每次 CI 的原版数据计算，**不写死 175 个类都能匹配**。

**证据边界：** 同名类文件路径是静态命名惯例证据，不代表 `DoInitAction` 的执行、运行时绑定、角色可选性或可见动画；即使导出类文件存在，也不能据此推导招式、碰撞箱或伤害。任何 1:1 复刻声明仍需原版逐帧、逐招式与完整流程验证。

## M1 增量：初始化标签位置取证

AS2 类路径候选报告现在同时保留每个零 ShowFrame Sprite 的静态 `DoInitAction` 标签位置：时间轴、零基帧号、解压后字节偏移及标签体长度，并对重复偏移和无效数值失败关闭。新增 `zero_sprite_init_tag_count` 与 `zero_sprites_with_verified_class_and_init_tag` 两个独立计数。

这使 FFDec 导出的类路径哈希和 SWF 初始化入口能在同一份元数据报告中按 `characterId` 对照。它仍不是脚本运行时调用关系，也没有独立解码或执行 AS2 字节码；报告不包含类名明文、脚本正文或原版素材。CI 不以固定的 192 作为普遍规则，真实结果由原版 SWF 和 FFDec 导出确定。
