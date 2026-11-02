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

## 原始 ButtonCondAction 头部完整性门禁

对每条已按 character ID 和解压后偏移配对的记录，重新从 SWF 原始解压字节读取 `CondActionSize`（小端 16 位）及 `CondFlags`（小端 16 位）。要求原始事件标志与已核验的来源记录一致；`CondActionSize=0` 必须与来源的末记录标志一致，非零长度必须等于 4 字节头部加动作字节数。即使来源记录和 FFDec 交叉表中的标志被同时改成相同的错误值，也不能绕过原始字节校验。

这只加固来源完整性，不验证 ActionScript 反编译等价性、分支运行可达性、按键行为或 1:1 战斗。仍不发布原始 SWF、AS2 正文或美术音频。

## 函数体字节范围定位（受限复核用）

对结构分层成功的 ButtonCondAction，新增 `bytecode_function_body_ranges`：仅包含 DefineFunction/DefineFunction2 的 opcode 类别、声明的解压后 SWF 绝对偏移、函数体的半开区间 `[body_start_uncompressed, body_end_uncompressed)` 和字节长度。偏移计算为原始动作容器头部位置 + 4 字节 + 分层解析器返回的相对位置。新增全局 `bytecode_function_body_byte_total_on_partitioned_records`，在 CI 中与逐条函数体长度闭合核验。

若某条动作流的结构分层失败，该记录的范围为 `null`（未验证），不能当成空函数表；合法无函数的动作流则为 `[]`。此数据用于在**受限环境**准确定位按钮 693、701、715 的原始函数体，再与 FFDec 输出交叉审查。只输出偏移、长度、opcode 类别，不输出函数名、ActionRecord 正文或素材；不会解析函数体指令、验证反编译语义或推断运行时可达性。源字节、原版导出仍不得公开。
