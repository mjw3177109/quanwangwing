# M1 — 原始按钮 ActionRecord 与 FFDec 词法函数候选对照

在受限 AS2 runner 上，先生成并校验 `button-action-evidence.json`、`button-ffdec-export-crosswalk.json` 和 `button-ffdec-lexical-audit.json`，然后运行：

```sh
python3 tools/build_button_bytecode_lexical_join.py \
  --swf 拳皇wing1.4.swf \
  --buttons build/as2-probe/button-action-evidence.json \
  --crosswalk build/as2-probe/button-ffdec-export-crosswalk.json \
  --lexical build/as2-probe/button-ffdec-lexical-audit.json \
  --output build/as2-probe/button-bytecode-lexical-join.json
python3 -m unittest discover -s tests -p 'test_button_bytecode_lexical_join.py' -v
```

工具按原始 character ID 与解压后 ButtonCondAction 偏移进行严格连接，重新读取原始 SWF 并检查 SHA-256、动作字节范围、事件标志、FFDec 导出哈希、词法统计闭合和不支持的运行时验证声明。结构分层使用仓库已有的 `partition_top_level_actions`，只统计顶层已声明的 DefineFunction / DefineFunction2，排除函数体被误扫成顶层记录的问题。

结果将每条记录标记为 `neither_detected`、`bytecode_only_candidate`、`lexical_only_candidate`、`both_present_unverified` 或 `source_partition_rejected`。分类差异用于定位受限环境中的原始字节码与 FFDec 反编译文本复核位置，**不代表两种表示必须具有相同的函数数量**，也不能据此推断 FFDec 错误、函数可执行性、角色动作或战斗判定。失败的结构解析明确标记，不冒充已验证。

CI 仅上传 JSON 元数据，绝不上传原始 SWF、FFDec 导出的 AS2 正文、美术、音频或函数名称。语义等价、Flash VM 运行路径、逐帧对照及 1:1 验收仍为未完成。
