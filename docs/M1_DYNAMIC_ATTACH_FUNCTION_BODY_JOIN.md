# M1：动态 attachMovie 标识符与函数体词法关联

本工具仅消费已验证的 FFDec AS2 元数据：dynamic-attach-assignment-sites.json、attach-identifier-references.json、dynamic-attach-reference-join.json。严格校验 SWF SHA-256、词法引用总量、未截断示例、原始路径哈希、赋值行号和未验证运行时状态；不读取、不上传原始 ActionScript。

运行：

    python3 tools/build_dynamic_attach_function_body_join.py --assignments build/as2-probe/dynamic-attach-assignment-sites.json --references build/as2-probe/attach-identifier-references.json --joined build/as2-probe/dynamic-attach-reference-join.json --output build/as2-probe/dynamic-attach-function-body-join.json

基于 2026-10-31 已下载的 AS2 metadata artifact，两个动态 attachMovie 参数标识符在三处原版函数赋值候选（第 349、379、404 行）中出现更强的词法结构关联：第 351、381、406 行的另一个标识符成员引用，分别落在以赋值目标标识符命名、起始行匹配的函数表达式候选体内。三处均通过哈希路径和词法作用域元数据交叉核对。

此证据不证明函数可达、动态参数的运行时值、角色创建关系或角色动作数据。FFDec 反编译产生的作用域仍可能不准确；下一步应在受限环境中分析函数体及实际调用链，并解决 -dumpAS2、-linkReport 超时。输出只含哈希、行号和语法分类，不包含原版脚本正文、美术或音频。
