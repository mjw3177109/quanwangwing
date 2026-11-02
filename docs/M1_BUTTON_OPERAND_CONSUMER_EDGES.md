# M1：原版按钮操作数消费者来源候选（仅元数据）

在既有原始 SWF SHA-256、函数体边界、ActionRecord、分支目标、候选栈深度及 ActionPush 字符串位置验证通过后，增加 **ActionPush/运算结果 → GetVariable、SetVariable、ActionIf** 的有界静态候选边。只报告解压后 SWF 的生产者/消费者指令偏移、ActionPush 元素序号、操作数角色、抽象类型及同一报告内的匿名 `S1/S2` 等价类；不导出原始字符串、数值、哈希或 ActionScript 正文。

```bash
python3 tools/build_button_operand_consumer_edges.py \
  --swf 拳皇wing1.4.swf \
  --join build/as2-probe/button-bytecode-lexical-join.json \
  --origins build/as2-probe/button-operand-origin-audit.json \
  --branches build/as2-probe/button-function-branch-audit.json \
  --output build/as2-probe/button-operand-consumer-edges.json
```

严格核对三个来源报告的 SWF SHA、函数覆盖、ActionPush 元素位置和分支目标。对已确认完整的函数体，沿两条条件分支进行有界抽象栈分析，去重记录变量名、赋值值、条件操作数的生产者候选；若来源不完整则返回 `null` 而非零条。遇到未知指令、非法字节范围、缺失分支、栈下溢或分析超限时直接失败，不把部分数据当作完整结果。

**限制：** 这是可能路径的静态来源图，不能断言 Flash VM 可达性、条件真假、具体变量含义、招式数值、FFDec 语义等价或 1:1 复刻。若没有明确素材授权，原始 SWF、角色图、音频和反编译源码仍只留在受限环境。新增 artifact 仅含 JSON 元数据。
