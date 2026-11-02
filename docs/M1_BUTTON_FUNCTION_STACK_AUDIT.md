# M1：按钮函数体候选栈深度审计

`tools/build_button_function_stack_audit.py` 以原始 SWF 字节、已验证的 `button-bytecode-lexical-join.json` 和静态 CFG 为输入，针对目前明确支持的 AS1/AS2 opcode 子集建立**有界的候选栈深度传播**。每个 ActionPush 只读取元素数量；对 Multiply、Modulo、GetVariable、SetVariable、Return、If、Jump 和 End 使用明确的最小出入栈数量，不输出任何字符串、数值或原始操作数字节。

运行：`python3 tools/build_button_function_stack_audit.py --swf 拳皇wing1.4.swf --join build/as2-probe/button-bytecode-lexical-join.json --output build/as2-probe/button-function-stack-audit.json`。

函数入口假设栈深为零；ActionIf 的真假分支都作为候选路径保留。每个候选状态由 `(ActionRecord 边界, 抽象栈深)` 表示。超过 4096 状态或 128 深度时标记 `analysis_limit_reached`，绝不将截断结果当作完整验证。无法建立源 CFG 时标记 `source_cfg_unresolved`。

`potential_underflow_record_count` 和 `divergent_entry_depth_record_count` 只用于定位需要 FFDec/原始字节码复核的候选路径：因为条件未求值，候选路径可能不可执行，**不能据此断言 Flash VM 栈错误**。`runtime_stack_verified` 与 `decompiled_semantics_verified` 始终为 `false`。此增量不是招式判定或 1:1 行为验收，也不公开原版素材。
