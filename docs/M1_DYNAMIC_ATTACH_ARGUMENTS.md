# M1：动态 attachMovie 首参数的静态来源候选

前一轮已经在 7,054 个 FFDec AS2 导出文件中发现 10 个 attachMovie 词法调用候选，其中 2 个无法用直接、未转义的字符串字面量映射到 ExportAssets。本轮只针对这类调用建立可审计的**参数形态与先前赋值候选**，不推断运行时实例化。

工具：python3 tools/build_attach_argument_provenance.py --scripts build/as2-probe/exports/scripts --export-index build/as2-probe/script-export-index.json --attach-evidence build/as2-probe/runtime-attach-evidence.json --asset-index build/as2-probe/asset-index.json --output build/as2-probe/attach-argument-provenance.json

工具重新逐文件验证长度与 SHA-256，并与上轮 attachMovie 元数据报告逐调用交叉核对。对动态首参数识别 identifier、member_reference、call_expression、concatenation、opaque_literal_or_empty 或其他表达式。简单标识符进一步扫描**同一文件、调用点之前**的词法赋值；若原报告存在函数范围候选，则以其起始行为扫描下界。

赋值右值只有直接未转义的字符串与 SWF ExportAssets 名称表匹配时，才输出已经公开在 ExportAssets 元数据中的符号名称及 ID。其他字符串只输出 SHA-256，标识符和完整表达式仅输出哈希；不公开 ActionScript 正文或新提取的原版素材。

严格局限：函数范围与赋值关联均为词法候选，可能受到作用域遮蔽、条件分支、变量重赋值、跨文件赋值、间接调用及 FFDec 反编译偏差影响。即使先前赋值匹配角色符号，也不能证明 attachMovie 实际使用该值，不能据此编造角色动作、伤害或碰撞箱。下一步应以原版运行时行为、实际脚本控制流和 Sprite 时间轴核实。
