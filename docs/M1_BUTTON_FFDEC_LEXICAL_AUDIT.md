# M1 — FFDec 按钮脚本词法证据（受限源文件）

在 M1 AS2 诊断工作流的 runner 上，先验证原始 SWF `ButtonCondAction` 与 FFDec 18.0.0 导出脚本的 72 条映射，再执行：

```sh
python3 tools/build_button_ffdec_lexical_audit.py \
  --scripts build/as2-probe/exports/scripts \
  --crosswalk build/as2-probe/button-ffdec-export-crosswalk.json \
  --export-index build/as2-probe/script-export-index.json \
  --output build/as2-probe/button-ffdec-lexical-audit.json
python3 -m unittest discover -s tests -p 'test_button_ffdec_lexical_audit.py' -v
```

工具逐条重新验证文件路径、原始 SWF SHA-256、事件标签与原始条件标志对应关系、FFDec 导出长度及 SHA-256，拒绝缺失、重复、额外的按钮导出和错误的“运行时已验证”声明。实际读取原始 `.as`，但只输出 JSON 元数据：已匹配函数作用域的数量及行范围、未匹配函数候选数、`if/else/switch/case/for/while/return` 词法标记数量、导出文件 hash 和来源偏移。

优先复核按钮 693、701、715，因其在之前结构感知与旧版入口图的访问记录数量比较中存在 13/13/13 条差异。这个优先级**不是**已证明的函数调用或战斗事件。

所有 ActionScript 原文、原版 SWF、美术与音频仍只在 runner 或受限环境保留，不进入公开 artifact。字符串和注释会遮蔽，但正则字面量、损坏的反编译代码和词法作用域启发式可能造成误报。**词法候选数不等于字节码函数数，不证明反编译等价，也不证明 Flash VM 的真实可达性。** 后续必须对受限原始反编译源码、ActionRecord 字节流和逐帧执行进行交叉验证。
