# HTML5 重构计划与验收标准

## 原则

- 原版 SWF 是事实来源；不凭印象重写动作、帧数、角色属性或 UI。
- 先解析，再建模；每项推断记录证据（脚本名、字符 ID、帧号、标签索引或导出文件）。
- 游戏逻辑以固定时间步推进，渲染帧率与战斗帧率分离。
- 每次提交只推进可验证的增量，不把占位动画当作完成内容。

## 里程碑

### M0 — 工程与分析环境
- [x] 检查仓库、原始 SWF、FFDec 文件。
- [x] 建立 Java 8 锁定的自动分析入口。
- [x] 建立 HTML5 引擎骨架与 Node 测试。
- [x] 在 GitHub Actions 上成功解析原始 SWF 结构并保存 metadata artifact（完整脚本/素材导出另行验收）。

### M1 — SWF 结构清点
- [x] 确认 SWF signature、版本、舞台宽高、帧率、总帧数（CWS v9，660×485，32 FPS，39 帧）。
- [x] 导出并统计所有 SWF tags（含 Sprite End 为 98,210；FFDec 展示 96,435）。
- [ ] 识别 AS1/AS2/AS3 脚本数量、入口帧与关键函数。
  - 已加入 DefineButton2 内嵌 ButtonCondAction 容器的字节级清点和入口偏移审计；仍未区分 AS1/AS2 函数，也未完成关键函数和运行时语义映射。
  - 已建立 DefineButton2 动作容器与静态 PlaceObject 引用的来源校验交叉表；静态引用不等于运行时按钮可达或输入行为。
- [ ] 完成 characterId / symbolClass / sprite / button / sound 的语义映射（已生成 14,562 个定义与 715 个 ExportAssets 名称的索引，仍需解析实际引用和动作）。
- [x] 生成可追溯的资源 metadata manifest 与 asset-index（无原版素材字节）。

### M2 — 角色与动作数据
- [ ] 识别全部可选角色、隐藏角色、场景和 UI 状态。
- [ ] 为每个角色建立逐动作帧表。
- [ ] 从脚本和形状/精灵结构定位攻击、受击、投技、倒地、胜利、败北动作。
- [ ] 提取并验证 hitbox、hurtbox、pushbox、位移、硬直、取消窗口和资源消耗。
- [ ] 将原始数值写入 JSON，不在运行时代码中硬编码猜测值。

### M3 — 视觉与声音
- [ ] 精灵图集与帧序列保持原始顺序。
- [ ] 对照原始舞台尺寸、锚点、缩放、镜像、层级、透明度与混合模式。
- [ ] 音效和 BGM 的触发帧、循环点、音量与声道对齐。
- [ ] 建立原版截图与 HTML5 截图的像素差异报告。

### M4 — 战斗系统
- [ ] 固定帧时钟、输入缓冲、指令识别与方向优先级。
- [ ] 普通技、必杀技、超必杀、投技、防御、闪避、受身等按原版实现。
- [ ] 命中/格挡/受击停顿、硬直、击退、浮空、倒地、连段和判定优先级。
- [ ] 双人本地键盘与 Gamepad 支持。
- [ ] 每个招式有自动化帧数据测试。

### M5 — 完整流程
- [ ] 标题菜单、模式选择、角色选择、场景选择、对战 HUD、暂停、胜负与再战流程。
- [ ] 所有可见文字、按钮状态、过场和转场与原版对照。
- [ ] 桌面与移动浏览器适配。

### M6 — 1:1 验收
每个角色、每个动作、每个场景和每个菜单都必须逐项检查：
- 舞台尺寸与帧率
- 动画帧数、顺序、锚点和播放速度
- 输入窗口、指令识别、优先级和缓冲
- 攻击判定、受击判定、推挤判定与伤害/硬直
- 音效/BGM 触发点
- UI 布局、文本、状态与转场
- 对战流程、胜负条件、计时与平局规则

只有全部关键用例通过原版对照，才能将版本标记为 1:1 验收通过。

## M1 当前证据补充（2026-11-05）

以下结果来自同一原始 SWF SHA-256 cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb，并由 Actions #41895140039 的受限 FFDec 导出与 Artifact #13355570986 复核：

- Java 为 1.8.0_504；FFDec 18.0.0 的 --phase scripts 成功，耗时 44 秒，导出 7,054 个 .as 文件、41,054,213 字节；126 个空文件均被核验为 no-op，unexpected empty 为 0。Artifact 仅含 28 个 JSON metadata 文件，不含 .as 源码。
- SWF 脚本入口报告包含 3,065 个 legacy action containers：Tag 12（DoAction）2,737 个、Tag 59（DoInitAction）328 个；ABC 容器为 0，FileAttributes AS3 标记为 false。当前可确认没有观察到 AS3 ABC 容器，但仅凭这些标签仍不能区分每个 legacy action 的 AS1/AS2 语言级版本。
- 语义候选索引覆盖 1,751 个候选脚本、199 个函数范围，未匹配函数候选为 0。词法标记计数为 attack 187、combo 222、guard 16、hitbox 2；collision、damage、knockback、move_state 均为 0。它们只是检索线索，不是运行时行为或数值证明。
- 角色交叉表有 16 个 base/type2 变体候选，关联 16 条 Sprite 时间轴；涉及 Iori、K、Kula、Kyo、Mai、Moriya、Orochi、Ryo 八个候选名称，不能据此认定八者均可选。角色脚本中有 45 个函数范围；attack/combo/keyboard/timeline_jump 词法标记分别为 36/43/22/25。
- 角色时间轴调用候选共 25 个：6 个字符串字面量、19 个动态或未解析参数。6 个字面量标签只在其他 Sprite 时间轴出现，且没有静态可达放置关系；19 个动态参数仍未解析，不能当作已确认的招式帧名。
- 两个 hitbox 词法候选文件名为 HitCheck_mc.as 与 hitCheck_obj.as；尚未证明其正文、实例放置、形状几何与战斗运行时之间的关系。
- 音频结构有 301 个 DefineSound、816 个 StartSound、1,551 个 SoundStreamHead；816 个 StartSound 中，125 个与同帧脚本容器并存、691 个没有同帧脚本容器。未发现未解析 soundId；同帧共存不等于脚本因果触发。

## 当前已知限制

SWF header、tag 清点、资源 metadata manifest、时间轴/声音静态索引及一次完整 FFDec 脚本导出已取得证据，但 M1 尚未完成。FFDec 18.0.0 的 -dumpAS2、-linkReport 历史上分别在 90 秒限制内超时；最新成功的 --phase scripts 只证明导出完整性，不等于函数语义已恢复。AS1/AS2 版本区分、19 个动态时间轴参数、角色是否可选、HitCheck 的实际几何与运行时绑定、音频因果触发及未知 tag 253/255 作用仍未验收。原始 SWF SHA-256 为 cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb。原始素材与 ActionScript 正文继续留在 runner/local，不进入公开 artifact。HTML5 Canvas 仍使用调试占位，未恢复原版角色、动画、UI 或战斗行为，尚未达到视觉/战斗 1:1。

## 下一轮优先任务

1. 先解析 19 个动态 gotoAndPlay/gotoAndStop 参数与 2 个动态 attachMovie 标识符，做同函数范围赋值/引用追踪；每条映射保留源文件哈希、行号、SWF 时间轴和偏移，未证明运行时绑定前不得升级为确定关系。
2. 重点核验 HitCheck_mc.as、hitCheck_obj.as 及相关 DefineSprite/PlaceObject/形状引用；只有能闭合实例、时间轴和几何证据时，才写 hitbox/hurtbox/pushbox 数据。
3. 将 16 个角色变体候选的函数调用、FrameLabel、静态放置关系与角色选择流程交叉核验；明确区分候选角色、可选角色和运行时实例。
4. 对 -dumpAS2 与 -linkReport 分开做有界重试并记录超时/退出码；继续区分 legacy ActionScript 版本与关键函数入口。当前 ABC=0，不要虚构 AS3 源码。
5. 完成 816 个 StartSound 与 301 个 DefineSound 的 ID、时间轴、帧、循环/流音频关系映射；125 个同帧脚本关联只作为优先审阅队列。
6. 上述证据闭合后，再按真实 characterId、Sprite 帧序列、矩阵、depth 和音频触发实现 Canvas 渲染；调试方块不得作为原版角色或完成度证据。
## M1 增量：逐帧引用与未知标签邻接证据

运行 `python3 tools/build_timeline_index.py --manifest build/swf-analysis/swf-manifest.json --output build/swf-analysis/timeline-index.json`。

逐时间轴记录 PlaceObject/PlaceObject2/PlaceObject3 的 characterId 与 depth、移除事件、FrameLabel、StartSound 的 soundId、DoInitAction 的目标 spriteId、脚本所在帧与解压后偏移。未知 Tag 253/255 只统计同一时间轴下一标签，不推断含义。该索引不包含原版位图、音效或 ActionScript 正文，也不能证明招式和碰撞箱已移植。
