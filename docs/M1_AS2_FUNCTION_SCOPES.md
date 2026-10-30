# M1 — AS2 函数范围与调用线索（仅元数据）

## 目的

将原版 FFDec 导出的 AS2 中的函数声明、函数赋值与 Key.isDown、hitTest、gotoAndPlay/Stop、attachMovie、onEnterFrame 等词法调用标记关联。上一阶段只能统计每个脚本的关键词数量，无法区分同一个脚本中不同函数的线索。本阶段在不发布原始 ActionScript 正文的前提下，记录函数名称、起止行、标记类别、调用行号及计数，便于人工回到原版核对。

## 实现与校验

- tools/as2_scope_evidence.py：对已经遮蔽注释和字符串的源码做括号/花括号匹配，识别具名函数、函数表达式赋值和可识别的 prototype / 事件回调。
- 每个标记只归属最内层匹配的函数；无法归属的标记单独统计，不凭空分配给外层函数。
- 无法确定函数体范围的候选保留在 unmatched_function_candidates 中，不把它当作已解析的函数。
- tools/build_as2_semantic_index.py：在已有 SHA-256/长度校验后生成 function_scopes 和 unscoped_marker_counts，并校验函数内外的标记总数与原有词法统计完全一致。
- tests/test_as2_scope_evidence.py：测试嵌套函数、具名函数表达式、返回类型、无函数体候选、源代码内容不泄漏、注释/字符串屏蔽。

## 运行

通过现有的 .github/workflows/m1-as2-export-probe.yml 在 Java 8 runner 上执行脚本导出与语义索引，生成 build/as2-probe/as2-semantic-index.json。上传的 artifact 只包含元数据，不含原版 .as 文件、图片、音效或原始导出日志。

## 局限

这仍是静态词法线索，不是完整 AS2 解析器或调用图。正则字面量、动态属性、反编译异常及复杂语法可能造成边界误判；行号只是定位线索。任何角色招式、输入指令、碰撞箱、伤害、硬直、帧时序必须再经原始 SWF 时间轴与运行行为验证，不能从标记数量直接推断。
