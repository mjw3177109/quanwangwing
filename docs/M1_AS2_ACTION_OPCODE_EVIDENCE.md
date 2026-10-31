# M1：原版 AS1/AS2 ActionRecord 字节码结构取证

本工具对原始 SWF 解压字节流中的 DoAction（12）与 DoInitAction（59）标签逐条验证 header、长度、原始偏移与初始化目标 Sprite ID，并按 SWF ActionRecord 编码规则统计顶层操作码。对于高位操作码读取 UI16 payload 长度；ActionEnd 之后的剩余字节只记录，不解释。所有统计由原始字节而非反编译推断产生。

运行：

```sh
python3 tools/build_as2_action_opcode_evidence.py --swf 拳皇wing1.4.swf --manifest build/swf-analysis/swf-manifest.json --output build/swf-analysis/as2-action-opcode-evidence.json
```

输出只含 SHA-256、操作码计数、帧号、标签偏移、函数定义记录候选数及终止标记。它不包含 ActionScript 正文、函数名称、原版音频或图像；可以作为受限 metadata artifact。顶层 ActionDefineFunction / ActionDefineFunction2 记录不等于可调用函数数量，嵌套函数体暂不解析。仅靠操作码无法可靠区分 AS1 与 AS2；ABC/AS3 另由 script-entry-evidence.json 统计。出现缺失 ActionEnd 或终止后尾部字节时必须保留异常记录，不得直接视为正常或丢弃。

下一步将这份原始操作码证据与 FFDec 的私有脚本导出交叉验证关键函数入口、调用关系及角色动作。M1 尚未完成，不据此宣称 HTML5 战斗已实现或达到 1:1。

## ActionEnd 后剩余字节的结构分类

从原版标签体中取出顶层 ActionEnd 后的尾部，按原始字节是否为 0 分类为 `none`、`zero_only`、`nonzero_only`、`mixed`，同时记录各类容器数、总字节数和尾部长度直方图。所有分类由原始 SWF 字节直接计算；与既有 3,065 个容器清单逐条对应，工作流执行闭合计数校验。

`zero_only` 只能称为“可能的填充”，不能认定可安全删除；`nonzero_only` 和 `mixed` 也不能直接认定为可执行脚本、嵌套函数或损坏数据。不会公开原始尾部字节、脚本正文或素材。下一阶段应在受限环境与 FFDec 的结构解析逐项交叉验证。


## 11 字节尾部的零位模式审计

对于顶层 ActionEnd 后长度**恰好 11 字节**的尾部，增加仅由 `0`（字节值为零）和 `x`（非零）组成的 11 位掩码直方图、零字节数量直方图，以及按 DoAction/DoInitAction 标签类型的分布。不会输出非零字节的实际值、ActionScript、字节码正文或原版素材。

这只是结构性聚类：相同零位掩码不等于相同内容，也不代表它们是相同函数、可执行 ActionRecord、填充或特定游戏事件。新增 CI 校验三个直方图的计数必须分别与既有尾部长度直方图中的 11 字节样本数量闭合。后续应结合受限 FFDec 导出与 SWF 结构规范确认其语义。

## ActionEnd 后 11 字节的二次 ActionRecord 边界探针

对 11 字节尾部**从首个顶层 ActionEnd 之后**尝试一次有界 ActionRecord 语法步进，统计四类候选：`terminated_at_end`、`terminated_with_remainder`、`no_terminator`、`invalid_record_boundary`。另统计语法步进成功样本的候选记录数量分布。测试及 Actions 验证各分类数量覆盖全部 11 字节尾部、有效样本记录数直方图闭合。

这不是对尾部的执行、反编译或语义认定：任意字节可能碰巧符合 ActionRecord 边界，首个 ActionEnd 后的字节也可能属于非脚本结构。不会导出原始字节、操作码序列、脚本或素材。只有在与受限 FFDec 结果及 SWF 规范交叉验证后，才能解释这些结构候选。
