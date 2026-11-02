# M1：原版按钮函数体操作数来源候选审计

本轮新增 `tools/build_button_operand_origin_audit.py`，在原始 SWF、已验证的函数体 ActionRecord、静态分支目标和候选栈分析基础上，进一步追踪 **ActionIf 条件操作数**及 **GetVariable/SetVariable 变量名操作数**的类型级来源。仅报告 `literal_string`、`literal_integer`、`variable_read_result`、`arithmetic_result` 等抽象标签，绝不导出实际字符串、变量名、整数值或 ActionScript 正文。

执行：

```bash
python3 tools/build_button_operand_origin_audit.py --swf 拳皇wing1.4.swf --join build/as2-probe/button-bytecode-lexical-join.json --output build/as2-probe/button-operand-origin-audit.json
```

原始字节 SHA、函数范围、opcode 直方图、分支目标和栈候选门禁由已有审计器复核。遇到未知/不完整来源时输出 `source_stack_unresolved`，超过状态/栈上限时输出 `analysis_limit_reached`，遇到候选路径栈下溢时输出 `candidate_underflow_detected`，不宣称完整。对后三种状态，单函数的 `if_operand_origin_counts` 与 `variable_name_operand_origin_counts` 均为 `null`，而不是容易误读为零的空字典；顶层来源总数仅累计完整的 `bounded_origin_candidates`。仍保留已确认的原始 opcode 数和探索状态数用于排查，但不把截断的部分来源计数冒充完整结果。来源计数是静态候选路径去重后的 **(指令偏移, 抽象类型)** 组合，既不是变量读写执行次数，也不是条件真假结果。

此工具尚未解析变量名、实际数据流别名、Flash VM 运行时行为或 FFDec 反编译语义；`runtime_behavior_verified` 与 `decompiled_semantics_verified` 恒为 `false`。不得用本报告推导招式伤害、帧数、碰撞箱或 1:1 完成度。原版 SWF、脚本和音频图像继续保持不公开再分发。

## M1 增量：ActionPush 字符串的跨函数等价类（不含原值）

`build_button_operand_origin_audit.py` 在原有来源、分支与有界栈验证全部通过的函数体中，额外读取原版 ActionPush 的字符串**原始字节等同性**。相同字节分配同一个报告内临时编号（如 `S1`），记录每个函数体中按压栈顺序出现的编号，以及各编号出现次数。只在内存中比较原始字节；输出 JSON **不包含字符串内容、原始字节、字符串哈希或 AS2 源码**。

该数据可帮助受限环境内的复核人员判断按钮函数是否复用相同的字符串常量，但**不能证明**这些常量是变量名、条件值、招式或 UI 文案，也不能证明 FFDec 语义和运行时行为。若来源分析超限、下溢或未解析，对应函数的等价类字段必须为 `null`，不得把部分证据当成完整结果。编号只在同一份报告中有意义，不能跨版本持久引用。
