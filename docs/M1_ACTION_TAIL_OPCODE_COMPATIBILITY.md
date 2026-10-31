# M1: ActionEnd 后 11 字节尾部的 ActionRecord 操作数兼容性取证

## 目的与边界

上轮从原始 SWF 得到 475 个长度为 11 的尾部，均可语法步进为
`L2>L2>End`。本轮只针对这些候选记录，检查 **ActionRecord 操作码是否属于
已知 SWF legacy Action 集**，以及固定长度操作数或 ActionPush 类型字段的
**字节结构兼容性**。这仍是静态语法证据，**不能证明尾部字节会被 Flash 执行**。

执行：

```bash
python3 tools/build_action_tail_opcode_compatibility.py \
  --swf 拳皇wing1.4.swf \
  --manifest build/swf-analysis/swf-manifest.json \
  --output build/swf-analysis/action-tail-opcode-compatibility.json
```

程序在读取前验证原始 SWF SHA-256 与 manifest 的一致性，并逐项检查
DoAction / DoInitAction 标签偏移、长度、脚本清单、初始化目标。
仅在首次顶层 ActionEnd 之后恰好有 11 字节时探测，且仅接受
两个 payload 长度均为 2 的 long ActionRecord 与末尾 End 标记。

## 统计口径

输出仅包含原始 SWF SHA-256、容器覆盖数量、候选数量、按标签分类的数量、
**操作数兼容性类别**及其二元组合计数。分类如下：

- `fixed_length_match` / `fixed_length_mismatch`：已知固定长度动作记录；
- `push_payload_well_formed` / `push_payload_invalid`：ActionPush 内部类型/长度字段的有界语法检查；
- `known_variable_payload_unchecked`：已知动作但复杂操作数尚未解码；
- `unlisted_long_opcode`：不在已列举的 legacy long Action 集合内，不能自动判定为无效。

不会输出原始操作码值、原始 operand、ActionScript 正文、SWF 片段、角色图像或音频。
所有分类都不能用来推断角色招式、伤害、硬直、动画或运行时执行顺序。

## CI 验收

`swf-analysis.yml` 将本报告与上一轮
`as2-action-opcode-evidence.json` 的 SHA-256、长度 11 样本数、
`L2>L2` 候选数进行交叉校验，并验证所有直方图闭合：

- `length11 = eligible + other_shape`
- `candidate_record_count = 2 * eligible`
- `sum(pair_histogram) = sum(tag_histogram) = eligible`
- `sum(record_class_histogram) = candidate_record_count`

实际类别与样本数量必须以 Actions 运行结果和 metadata artifact 为准，
不在文档中预填或猜测。原版资产与源码继续留在受限运行环境中。

## M1 控制流补充（本轮）

新增有界静态审计：在首次 ActionEnd 前的**顶层** ActionRecord 中，只对
Jump/If 的两字节有符号相对偏移计算目标位置，并判断是否跳过 End 指向
11 字节候选尾部的第 1、2 条记录或终止符。候选尾部内的 Jump/If 同样
按相对目标分类；GotoFrame 的操作数是帧号，不是分支位移。

报告仅增加操作类别、分支目标类别、顶层前置分支数的直方图，不输出
原始 opcode、跳转位移或任何脚本/媒体内容。函数体、With/Try 内嵌动作
不在本次顶层扫描范围。静态目标对齐**不证明运行时可达或被 Flash 执行**。

## M1 有界静态图补充（2026-11-01）

在已有 11 字节尾部候选上，从脚本首条顶层 ActionRecord 建立 Jump / If / 普通顺序流的有界静态图。首次 ActionEnd、Return、Throw 为终止节点；仅对**完整记录边界**建立分支边，非法或无法对齐的目标只计数不跟随。分别统计 0/1/2 条尾部候选记录被静态图访问的容器数、尾部终止符、首次 End 及前置分支入边。全部结果为汇总计数，不导出原始字节、操作码或脚本正文。

**限制：** 此图不解析嵌套函数体、不建模 WaitForFrame 的跳过行为、异常控制流或动态调用，且条件分支两侧都按可能执行处理。因此“静态图可达”不等于 Flash 运行时执行，“静态图不可达”也不等于原版永远不会执行。所有数字以 CI 实际 SWF 分析 artifact 为准，不预填结论。

## M1 未解析分支目标分类补充（2026-11-01）

在既有有界顶层静态图中，将**不能落在完整 ActionRecord 起点**的分支边按目标归入：首次 End 前的记录内部、11 字节尾部记录内部、容器前、容器后，以及操作数长度不合法。分别记录全部未解析边与“起点节点已被简化静态图访问”的未解析边，按类别汇总；不导出目标偏移、操作码、脚本或原始字节。

CI 验证各类别总和等于未解析边总数，且每类已访问源节点的边数不超过该类总数。分类只能帮助定位当前解析器的盲区，**不是 Flash 运行时可达性证明**。所有原版数量以实际 Actions artifact 为准。

## M1 未解析前置记录内部目标的字节区域（2026-11-01）

针对既有静态图中 `pre_end_record_interior` 类别，进一步按已解析的顶层
ActionRecord 边界区分：`length_field`（长格式记录的两字节长度字段）、
`payload`（长格式记录的操作数区域）和 `unclassified`（未能定位到已解析记录）。
不导出原始目标偏移、操作码或 payload；每条未解析内部目标只计入一个类别。

CI 强制检查三类计数之和恰好等于 `pre_end_record_interior` 的边数。
分类是静态字节布局证据，**不意味着这些地址是有效的 Flash 跳转入口**，
也不能排除嵌套函数、WaitForFrame、异常或动态执行造成的分析盲区。
原版计数仅以对应 Actions artifact 为准，不在文档中预填。
