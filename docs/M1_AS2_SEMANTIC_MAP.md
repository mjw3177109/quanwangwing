# M1 — AS2 角色/入口候选语义索引

本阶段将已验证的 FFDec ActionScript 导出与原始 SWF 的 ExportAssets 角色类候选关联。这是可追溯的静态线索，不是已经复刻的招式、碰撞箱或状态机。

## 输入与证据链

- 原始 SWF SHA-256：cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb。
- build/as2-probe/script-export-index.json：来自独立 AS2 导出，记录每个文件相对路径、长度、SHA-256，126 个空文件已与 ActionEnd-only 交叉验证。
- build/as2-probe/asset-index.json：来自 swf-manifest.json 中的 ExportAssets，包含八个角色类候选及其 base/Type2 characterId。
- build/as2-probe/exports/scripts/：FFDec 在临时 runner 上导出的原版脚本，不作为公开 artifact 发布。

## 自动检查

在同一 runner 上逐文件核对 AS2 源文件的长度与 SHA-256，拒绝来源 SHA 不一致、路径穿越、重复路径及不可解释的空导出。然后仅对角色类候选、名称可能关联战斗系统的 __Packages 文件、较大的帧脚本提取：

- class / extends / function 的标识符与行号；
- Key.isDown、hitTest、gotoAndPlay/Stop、attachMovie、onEnterFrame、onClipEvent、定时器等词法命中计数；
- 与角色候选 __Packages.<角色>_role / Type2_<角色>_role 对应的源文件存在性和哈希。

输出 as2-semantic-index.json 只包含元数据，不包含任何 ActionScript 源码正文或原始素材。识别结果可能受 FFDec 反编译质量、动态调用、注释、正则字面量等影响；名称匹配不证明角色可选，也不证明某函数的实际行为。

## 手动复现

先执行 python3 tools/analyze_swf.py --phase scripts --timeout 45 --output build/as2-probe，按 .github/workflows/m1-as2-export-probe.yml 生成 script-export-index.json，再执行：

python3 tools/build_asset_index.py --manifest build/as2-probe/swf-manifest.json --output build/as2-probe/asset-index.json

python3 tools/build_as2_semantic_index.py --scripts build/as2-probe/exports/scripts --export-index build/as2-probe/script-export-index.json --asset-index build/as2-probe/asset-index.json --output build/as2-probe/as2-semantic-index.json

下一步：优先核查角色初始化与状态转换、键盘映射、hitTest 调用所在函数，再以原版 SWF 的时间轴/运行行为交叉验证。不得凭关键词直接填充攻击判定、伤害或招式帧数。

## M1 后续增量：函数赋值形式与核心运行时脚本

AS2 可能使用 `Class.prototype.method = function(...)`、`this.onEnterFrame = function(...)` 等函数表达式赋值，而不仅是 `function method(...)` 声明。静态索引现在额外输出 `assigned_functions` 的目标标识符、行号及类别（prototype_method/event_callback/function_assignment），并统计总量。**这些仍是词法候选，绝非已确认招式。**

同时将经哈希与最小长度门禁验证的 `__Packages/role_corn/Role.as` 纳入候选语义索引；此前仅验证其完整性却未检查其方法形式。PR 检查会在临时 runner 上重新导出并生成 metadata-only artifact，源文件正文不上传。

后续必须逐项核查函数赋值与原版 SWF 时间轴、事件和运行行为的关联，不能仅凭函数名称填写伤害、hitbox 或动作帧数。
