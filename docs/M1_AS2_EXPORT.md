# M1 — FFDec ActionScript 2 源码导出验证（2026-10-30）

原版 SWF SHA-256：cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb。

## 已验证

- GitHub Actions run 41001157724（https://github.com/mjw3177109/quanwangwing/actions/runs/41001157724）使用 Java 1.8 和仓库随附 FFDec 18.0.0，执行独立 scripts 阶段。
- FFDec script_export 退出码 0，未超时，耗时 46.8 秒；报告 scripts_complete=true，无已识别错误标记。
- 导出 7,054 个 .as 文件，全部保留在 Actions 临时 runner，没有上传源代码、音频或图片。
- 第二次严格检查 run 41001372972 发现 7,054 个导出中有 126 个零字节 .as 文件。逐项交叉核对原版 SWF metadata 与 FFDec tag dump，126 个均对应唯一的 1 字节 DoAction tag，且 payload 为 0x00（ActionEnd），是可解释的空操作脚本，不应简单认定为反编译失败。修复后的 CI run 41001614469（https://github.com/mjw3177109/quanwangwing/actions/runs/41001614469）已直接验证原始解压字节与文件名/帧号关联：126 个空文件全部为 ActionEnd-only，无法解释的空文件为 0。7,054 个文件总计 41,054,213 字节，逐文件 SHA-256 与长度保存在 metadata-only artifact 中。

## 未完成

成功导出 7,054 个文件不等于 7,054 个脚本均已正确还原，也不等于游戏逻辑已经移植。仍需检查反编译警告、语法完整性、类间引用、事件回调、角色动作入口、攻击判定与状态转移；需要与原版行为交叉验证。此前 -dumpAS2 和 -linkReport 超时的问题不能据此宣称已经修复，只是找到一条可用的独立导出路径。

## 使用与保密

独立运行：python3 tools/analyze_swf.py --phase scripts --timeout 45 --output build/as2-probe

导出文件仅用于本地/临时 runner 的合法分析；公开仓库只存脚本计数、相对路径、文件长度与摘要，不公开反编译 ActionScript 正文。是否有再分发权需单独确认。


## 2026-10-30 新发现：相同 SWF 的 FFDec 导出并非逐文件稳定

独立下载并比较两次 metadata-only artifact：

- Run 41001614469：7,054 个 .as，总字节数 41,054,213；__Packages/role_corn/Role.as 为 258,954 字节，SHA-256 64d66bd9cb3d909442a89d13ad557d621867b394f5946128ba02f8e1b564f253。
- Run 41001777334：同一 SWF SHA-256、同样 7,054 个文件，总字节数 40,795,403；仅 __Packages/role_corn/Role.as 发生变化，缩小为 144 字节，SHA-256 525571fc636a2838b4e861cf214fd1556e93681e50d4a3dec2357513907f4b45。
- 两次均报告退出码 0、空脚本解释通过。故 **文件数量和单次运行内部 SHA 校验不足以证明导出完整**，此前“全部 7,054 个脚本完整”的结论需收窄为“文件数量和空脚本已验证”。

新的 AS2 静态索引门禁要求该关键 Role.as 文件存在、长度至少 100,000 字节（保守的回归阈值，非原版语义正确性证明），并将 FFDec 单脚本超时由 5 秒提高到 60 秒。若仍发生不稳定输出，应在 CI 失败后调查并继续修复，不能绕过门禁。
