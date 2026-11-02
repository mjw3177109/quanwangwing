# M1：按钮函数体静态控制流候选图

`tools/build_button_function_cfg_audit.py` 从原版 SWF 重新验证函数体与 ActionIf/ActionJump 目标，建立**保守的语法路径候选**。只允许 Push、Multiply、GetVariable、SetVariable、Modulo 的顺序流，Return/ActionEnd 终止，Jump 只走目标，If 同时保留目标与顺序路径。遇到未知 opcode 或非法目标，整张函数图标记 unresolved，不宣称完整静态可达性。

运行：`python3 tools/build_button_function_cfg_audit.py --swf 拳皇wing1.4.swf --join build/as2-probe/button-bytecode-lexical-join.json --output build/as2-probe/button-function-cfg-audit.json`。

静态候选不等于 Flash VM 实际执行、栈条件求值、函数调用关系或 FFDec 语义等价；不输出原始字节、操作数、反编译正文、美术和音频。仍未达到逐帧逐招式 1:1。
