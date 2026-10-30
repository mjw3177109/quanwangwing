# M1 — 未知 SWF Tag 253/255 的只读结构取证

## 目标与范围

原版 SWF 的结构清点发现 2,729 条 tag 253 和 1 条 tag 255。它们的含义尚未解码，不能假定为可忽略的填充内容。新增独立、只读的证据生成器，将未知 tag 的头部重新与原始解压后字节校验，避免仅凭解析器生成的 manifest 重复引用未经验证的偏移。

## 运行

在仓库根目录执行：

python3 tools/build_unknown_tag_evidence.py --swf 拳皇wing1.4.swf --manifest build/swf-analysis/swf-manifest.json --output build/swf-analysis/unknown-tag-evidence.json

输出包含每条未知 tag 的时间轴、帧号、解压后偏移、长度、SHA-256 摘要、同一时间轴前后 tag 类型；另统计各类型的长度分布、唯一 payload 摘要数、重复摘要和邻接类型组合。对 CWS/FWS 均使用解压后的偏移，长 tag 头部也会独立校验。

## 验收

- 校验原始 SWF SHA-256 与 manifest 一致。
- 逐条核对 tag 编码、头部长度、payload 起点、结束边界。
- 统计数量必须与原始 manifest 中 253/255 的记录一致。
- 单元测试覆盖 FWS/CWS、嵌套 Sprite、长 tag 头部、篡改 manifest、数量不符；在原版 SWF 可用时额外验证 2,729 + 1 的基线。
- GitHub Actions 上传 metadata-only JSON，不上传未知 tag payload、原版图片、音频或反编译源码。

**注意：SHA-256 重复只表示字节内容一致，邻接也只表示位置关系，不能证明未知 tag 的实际用途。** 后续需将这份索引与 FFDec 日志、动作时间轴、DoAction/DoInitAction 和真实运行行为交叉验证。
