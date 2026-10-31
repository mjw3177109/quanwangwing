# M1：动态 attachMovie 哈希标识符与角色脚本候选交叉审计

对 FFDec 完整导出的 AS2 metadata 做静态、只读关联：`attach-argument-provenance.json`、`attach-identifier-references.json` 与 `role-zero-frame-init-join.json`。逐项校验 SWF SHA-256、已验证脚本文件数与总字节、动态调用数量、标识符目标、调用位置、词法出现次数与角色脚本哈希。

运行：

```bash
python3 tools/build_dynamic_attach_reference_join.py \
  --provenance build/as2-probe/attach-argument-provenance.json \
  --references build/as2-probe/attach-identifier-references.json \
  --roles build/as2-probe/role-zero-frame-init-join.json \
  --output build/as2-probe/dynamic-attach-reference-join.json
```

在 PR #28 的实际受限 artifact 上离线验证：2 条动态调用均为拼接表达式，涉及 2 个不同哈希标识符，共有 20 处词法出现。两处调用均不位于已哈希确认的 16 个角色候选脚本中；两个标识符在对应调用之前均未发现同脚本词法出现（这不代表没有运行时赋值）。每个标识符在其他脚本中分别出现 8、7 次。

输出仅包含脚本路径 SHA-256、原版脚本 SHA-256、行号、参数与标识符 SHA-256、出现次数和范围分类。**不能**将词法关联当作真实变量绑定、运行时调用链、角色选择、招式或碰撞箱证据。原始 ActionScript 正文、明文脚本路径、原版美术、音频均不进入 artifact。
