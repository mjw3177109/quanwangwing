# M1：原版按钮函数体分支目标静态审计

## 范围

`tools/build_button_function_branch_audit.py` 仅处理此前已通过原始 SWF SHA-256、ButtonCondAction 来源及函数体 ActionRecord 结构验证的区间。读取 `button-bytecode-lexical-join.json` 中的半开函数体范围，重新读取解压后的原始 SWF 字节，并再次校验函数体记录数与 opcode 直方图。

只针对 ActionJump (0x99) 和 ActionIf (0x9D) 的 2 字节有符号相对跳转偏移计算静态目标：目标 = 当前 ActionRecord 结束位置 + 有符号偏移。输出解压后 SWF 绝对偏移，不输出原始操作数或脚本正文。

目标分类：`record_start`（目标是函数体内 ActionRecord 起点）、`body_end`（目标等于函数体末尾）、`outside_body`（目标超出函数体）、`non_record_boundary`（落在函数体内但不是记录起点）、`invalid_operand_length`（分支指令不是 2 字节偏移）。异常目标只作为待审计证据，不能擅自改写原版指令。

## 运行

```bash
python3 tools/build_button_function_branch_audit.py \
  --swf 拳皇wing1.4.swf \
  --join build/as2-probe/button-bytecode-lexical-join.json \
  --output build/as2-probe/button-function-branch-audit.json
```

受限 AS2 工作流中校验分支数量与原始 opcode 统计闭合，artifact 只包含 JSON 元数据。若函数体分层失败，明确计入 rejected，不伪造已验证分支。

## 证据边界

静态跳转目标不证明该分支可达、条件为真、Flash VM 实际执行，也不证明 FFDec 反编译语义等价。尚未恢复角色动作、碰撞箱、音频触发或 1:1 战斗行为。原始 SWF、FFDec 导出的 AS 源码和媒体素材不得自动公开发布。
