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
