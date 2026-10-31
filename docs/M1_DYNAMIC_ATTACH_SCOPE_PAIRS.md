# M1：动态 attachMovie 标识符跨脚本词法邻接审计

输入 FFDec 已验证的 metadata：attach-identifier-references.json 与 dynamic-attach-reference-join.json。只比较两个不同哈希标识符在同一脚本内的行号，统计最近行距不超过 2、5 行的脚本数量，并分类最近一对引用的词法函数范围。

运行：python3 tools/build_dynamic_attach_scope_pairs.py --references build/as2-probe/attach-identifier-references.json --joined build/as2-probe/dynamic-attach-reference-join.json --output build/as2-probe/dynamic-attach-scope-pairs.json

若词法示例截断、原始 SWF SHA-256 不一致、引用数量不符或存在未经证实的运行时绑定声明，工具直接失败。

输出仅包含哈希脚本路径、哈希标识符、行号、最近行距及汇总。不会发布原版 ActionScript、明文脚本路径、美术或音频。同一文件相邻行或相同函数候选不证明变量赋值、数据流、角色可选性或 1:1 实现。
