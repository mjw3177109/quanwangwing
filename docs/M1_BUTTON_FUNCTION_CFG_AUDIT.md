# M1：按钮函数体静态控制流候选图

`tools/build_button_function_cfg_audit.py` 从原版 SWF 重新验证函数体与 ActionIf/ActionJump 目标，建立**保守的语法路径候选**。只允许 Push、Multiply、GetVariable、SetVariable、Modulo 的顺序流，Return/ActionEnd 终止，Jump 只走目标，If 同时保留目标与顺序路径。遇到未知 opcode 或非法目标，整张函数图标记 unresolved，不宣称完整静态可达性。

运行：`python3 tools/build_button_function_cfg_audit.py --swf 拳皇wing1.4.swf --join build/as2-probe/button-bytecode-lexical-join.json --output build/as2-probe/button-function-cfg-audit.json`。

静态候选不等于 Flash VM 实际执行、栈条件求值、函数调用关系或 FFDec 语义等价；不输出原始字节、操作数、反编译正文、美术和音频。仍未达到逐帧逐招式 1:1。

## ActionPush 操作数结构检查（本次增量）

对已由原始 SWF 验证边界的 `ActionPush (0x96)`，进一步按 SWF 类型标记检查每个元素的长度：以零字节结尾的字符串、固定宽度数值、寄存器、布尔值、常量池索引及无附加字节的 null/undefined。只输出**类型计数**和结构异常数量，绝不输出实际常量、字符串、操作数字节或反编译源码。

如果遇到未知类型、截断的固定宽度元素或未终止字符串，将该函数体标记 `unresolved_opcode_or_target`，并增加 `invalid_push_payload_count`，不再宣称静态图完整。汇总字段 `push_operand_type_totals`、`invalid_push_payload_total` 由 CI 对照逐函数统计进行闭合校验。

此检查只证明操作数边界符合已识别的 ActionPush 编码形式；**不会**推导栈值、条件真假、函数调用或 FFDec 语义等价，也不会把静态候选当作运行时路径。
