# M1: 动态挂载标识符的函数作用域候选

在已通过 SWF 来源哈希、7,054 份 AS2 导出文件逐文件 SHA-256 校验的跨脚本引用索引中，新增函数签名和函数体的词法上下文。复用现有 AS2 函数识别规则，区分参数声明候选、函数体引用、签名其他引用和未归入函数的引用；嵌套函数优先选择最内层候选。报告记录函数名 SHA-256、函数类型及起止行，不写入新的原版标识符明文。

入口：`tools/as2_reference_scopes.py`；调用方：`tools/build_attach_identifier_references.py`。CI 检查每个目标的 `scope_context_counts` 总和等于原有词法命中数，并禁止将任何函数范围候选标记为运行时已验证。原有 `attach-identifier-references.json` 继续作为 metadata-only artifact 上传，原版脚本、美术、音频不公开。

**限制**：这是带来源的词法候选，不是 ActionScript 变量绑定、函数调用图或控制流证明。正则字面量、异常反编译文本、同名参数遮蔽、跨脚本作用域及运行时动态属性可能导致分类不完整。不能据此断言第 17 帧两处动态 `attachMovie` 的最终角色名称、招式、碰撞或数值。
