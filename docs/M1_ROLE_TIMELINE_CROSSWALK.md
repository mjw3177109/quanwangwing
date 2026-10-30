# M1 — 角色类、AS2 函数范围与 Sprite 时间轴交叉索引

本增量在**同一份 SWF SHA-256** 下，交叉核对三类已经验证的元数据：

1. asset-index.json 中由原版 ExportAssets 名称和 characterId 识别的角色类候选；
2. as2-semantic-index.json 中经文件 SHA-256 与长度验证的 FFDec 导出脚本路径、函数范围、词法标记；
3. timeline-index.json 中由原始 SWF 标签解析的 DefineSprite 时间轴、帧数及脚本/显示/声音事件数量。

执行：

    python3 tools/build_role_crosswalk.py --asset-index build/as2-probe/asset-index.json --timeline-index build/as2-probe/timeline-index.json --semantic-index build/as2-probe/as2-semantic-index.json --output build/as2-probe/role-crosswalk.json

CI 会在临时 Java 8 runner 上重新导出并验证 AS2 源文件，再生成 role-crosswalk.json 作为**仅元数据**的 artifact。不会上传 .as 正文、位图、音效或 FFDec 原始日志。

输出每个 base/Type2 角色候选的 ExportAssets characterId、验证过的脚本路径/哈希、词法函数名称/行号/标记，以及是否存在相同 characterId 的 DefineSprite 时间轴。如果没有对应时间轴，明确记录 null，不会猜测。脚本和 Sprite 之间只有 ExportAssets ID 的静态交叉引用，**不等于证明函数控制某个动作**。

验收门禁：三份来源 SHA 必须相同，所有 ExportAssets 角色候选必须有验证过的脚本路径与摘要；重复映射、缺失脚本、函数标记行号越界均失败。既有 16 个角色变体候选数量仍需在真实 SWF 的 CI 中验证，测试夹具不以数量 16 硬编码通用解析器。

## 尚待验证

- 角色是否真正可选、是否存在隐藏角色；
- 哪个函数对应哪个动作、动作帧及帧时序；
- 输入映射、伤害、碰撞箱、取消窗口、音频触发点；
- 未知 Tag 253/255 的真实语义；
- FFDec -dumpAS2 与 -linkReport 的超时。

这些均不得凭名称或词法命中数推断，必须回到原版 SWF 和运行行为验证。
