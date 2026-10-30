# M1 — FFDec ActionScript 2 源码导出验证（2026-10-30）

原版 SWF SHA-256：cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb。

## 已验证

- GitHub Actions run 41001157724（https://github.com/mjw3177109/quanwangwing/actions/runs/41001157724）使用 Java 1.8 和仓库随附 FFDec 18.0.0，执行独立 scripts 阶段。
- FFDec script_export 退出码 0，未超时，耗时 46.8 秒；报告 scripts_complete=true，无已识别错误标记。
- 导出 7,054 个 .as 文件，全部保留在 Actions 临时 runner，没有上传源代码、音频或图片。
- 后续增加逐文件相对路径、字节数、SHA-256 的 metadata-only 索引，并检查 7,054 个文件是否均非空。这个更严格的检查须以新的 CI run 为准。

## 未完成

成功导出 7,054 个文件不等于 7,054 个脚本均已正确还原，也不等于游戏逻辑已经移植。仍需检查反编译警告、语法完整性、类间引用、事件回调、角色动作入口、攻击判定与状态转移；需要与原版行为交叉验证。此前 -dumpAS2 和 -linkReport 超时的问题不能据此宣称已经修复，只是找到一条可用的独立导出路径。

## 使用与保密

独立运行：python3 tools/analyze_swf.py --phase scripts --timeout 45 --output build/as2-probe

导出文件仅用于本地/临时 runner 的合法分析；公开仓库只存脚本计数、相对路径、文件长度与摘要，不公开反编译 ActionScript 正文。是否有再分发权需单独确认。
