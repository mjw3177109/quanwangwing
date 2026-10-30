# M1：AS2 attachMovie 运行时挂载线索

前一轮角色引用索引确认 16 个角色符号都有 DoInitAction 目标引用，但当前显式 PlaceObject 引用为零。这不能证明角色使用 attachMovie，因此本阶段新增一个**可证伪的静态调用点清点**。

在同一 Java 8 + FFDec runner 上，以 script-export-index.json 的逐文件 SHA-256 和长度校验全部导出的 .as 文件，再用掩码过滤注释和字符串中的伪调用，定位 attachMovie(...) 词法调用候选。对首参数仅识别未转义的直接字符串字面量，和原始 SWF ExportAssets 名称表匹配；动态表达式不猜测。只输出已存在于 ExportAssets 的名称、characterId、是否属于已验证角色符号、脚本路径/哈希/行号以及可选的函数范围候选。未匹配的字面量只输出 SHA-256，不公开字符串正文。

运行：

\`\`\`sh
python3 tools/build_runtime_attach_evidence.py \
  --scripts build/as2-probe/exports/scripts \
  --export-index build/as2-probe/script-export-index.json \
  --asset-index build/as2-probe/asset-index.json \
  --crosswalk build/as2-probe/role-crosswalk.json \
  --semantic-index build/as2-probe/as2-semantic-index.json \
  --output build/as2-probe/runtime-attach-evidence.json
\`\`\`

CI 将结果保存为仅含元数据的 artifact。检查不同证据索引是否来自同一 SWF、文件哈希是否匹配、角色 ID 是否存在；无法识别的调用保持为 dynamic_or_unresolved，不把它强行映射到角色。

**局限：** 静态调用点不是实际执行轨迹；字符串变量、间接调用、动态类加载、继承与 ActionScript 反编译偏差可能导致漏检。即便匹配到角色符号，也不能证明角色可选、实例已创建、动画帧、伤害、碰撞箱或招式逻辑。下一步要以原版运行行为与真实时间轴交叉验证。
