# M1：按钮字节码与 FFDec 词法语义复核队列

本增量生成可追溯的**人工语义复核队列**，将原始 SWF 的 DefineFunction 函数体证据、FFDec 事件级词法统计、导出脚本 SHA-256 和操作数来源候选合并。工具严格校验同一 SWF SHA-256、按钮事件偏移、FFDec 导出路径与内容 SHA-256、函数体来源覆盖。

运行：

```bash
python3 tools/build_button_ffdec_semantic_review_queue.py \
  --join build/as2-probe/button-bytecode-lexical-join.json \
  --lexical build/as2-probe/button-ffdec-lexical-audit.json \
  --crosswalk build/as2-probe/button-ffdec-export-crosswalk.json \
  --origins build/as2-probe/button-operand-origin-audit.json \
  --output build/as2-probe/button-ffdec-semantic-review-queue.json
```

输出只包含需要人工复核的按钮、原始函数声明数、原始函数体 ActionIf 指令数、FFDec **整个按钮事件**的 `if` / `return` 词法关键词数、来源状态与已验证导出哈希。FFDec 事件级关键词**不能与嵌套函数体 opcode 一一对应**，因此任何差异都不等于 FFDec 反编译错误；`decompiled_semantics_verified` 和 `runtime_behavior_verified` 始终为 false。

下一步在受限 runner/本地读取对应 AS2 源码，逐项人工对照原始函数作用域、分支条件、变量与调用关系；验证前不把该队列当作动作数据或 1:1 证据。队列不包含原版 SWF 字节、脚本正文、美术、音频或操作数值。

## M1 增量：函数体精确复核坐标

复核队列中的每条候选事件现包含 `source_function_scopes`：原始 SWF 解压后字节流中的 DefineFunction 声明偏移、函数体半开区间 `[start, end)`、长度、结构解析状态、操作数来源状态和原始 ActionIf 指令数。生成时校验声明位置、范围顺序和长度闭合；异常来源直接失败，不会生成看似完整的复核坐标。

审核人员可使用这些坐标在受限环境定位原始函数体，再对照同一条队列中的 FFDec 导出路径与 SHA-256，避免将整个按钮事件的 `if` 关键词数误当成嵌套函数的分支数。结构解析被拒绝时，`operand_origins_complete` 必须为 false。坐标是**静态定位证据**，不是脚本语义、角色动作或 Flash VM 执行结果。不得公开对应原始字节或脚本正文。

## M1 增量：事件边界与操作码来源闭合

复核坐标还必须位于对应的原版 `ButtonCondAction` 有效负载范围内。范围上界使用已经与原始 SWF 字节核对的 FFDec crosswalk `source_action_byte_length`，负载起点为 `action_offset_uncompressed + 4`（两个 16 位头字段）。函数声明不能落在头字段中，函数体不能跨越事件末尾；同一事件中顶层函数范围不得重叠。

对结构已成功分区、操作数来源状态为 `bounded_origin_candidates` 的函数，额外核对原始 ActionRecord opcode 直方图的总数，以及 `GetVariable (0x1c)`、`SetVariable (0x1d)`、`ActionIf (0x9d)` 与来源分析的指令数。缺失或不一致时拒绝生成复核队列。该约束仅防止不同来源的静态证据被错误拼接，**不代表变量、条件或 FFDec 反编译语义已被证明**；仍不输出脚本正文、操作数或媒体。

## M1 增量：FFDec 条件分支行号定位（仅元数据）

`build_button_ffdec_lexical_audit.py` 现对经过 SHA-256 校验的 FFDec 按钮事件源码记录 `if` / `return` 词法命中行号（从 1 开始）。字符串和注释先屏蔽；同一行的多次命中保留重复行号，故行号数组长度与事件级关键词计数一致。`build_button_ffdec_semantic_review_queue.py` 对计数、排序、类型和缺失证据执行失败即停止的检查，并在受限复核队列中提供 `ffdec_event_lexical_if_line_numbers`、`ffdec_event_lexical_return_line_numbers`。

审核人员可用原始 SWF 函数体字节偏移及 FFDec 导出路径/哈希定位同一事件，再用行号查看 FFDec 反编译输出的分支位置。**这些行号属于整个 FFDec 按钮事件，不能直接对应原始嵌套 DefineFunction 的 `ActionIf`，也不能证明两个表示的语义一致。** 未导出任何脚本行文本、操作数、图片或音频；原版内容仍须留在受限环境。

## M1 增量：FFDec 事件关键词的候选函数体归属

受限 FFDec 词法审计现按**字符偏移**（不是仅凭行号）将 `if` / `return` 命中分为 `inside_recognized_function` 和 `outside_recognized_function`。嵌套函数内的命中只计一次，同一行的函数外命中不会误归入函数体。结果通过 `lexical_branch_keyword_scope_counts` 进入元数据 artifact，复核队列以 `ffdec_event_lexical_if_scope_counts` / `ffdec_event_lexical_return_scope_counts` 暴露计数，并要求两类之和严格等于已核验的事件关键词数；缺失、负数、布尔值或不闭合证据均拒绝。

此分类仅用于区分 FFDec **整个按钮事件**中的词法候选范围，不把函数外关键词映射成原始嵌套 DefineFunction，也不推断反编译缺陷或运行时执行。词法括号匹配和正则字面量仍可能导致误判。原始脚本、字节码、图像及音频不进入 artifact。
