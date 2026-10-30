# M1：角色符号直接引用与 DoInitAction 目标

本增量在同一原版 SWF SHA-256 下，结合已验证的角色 crosswalk 和逐帧 timeline index，生成 role-reference-evidence.json。只记录显式 PlaceObject / PlaceObject2 / PlaceObject3 中的角色 characterId，以及 DoInitAction (Tag 59) 指向的角色 Sprite ID。

每条证据保留父时间轴、帧号、解压后的标签偏移、tag code；显示引用额外记录深度和 move 标志。未携带 characterId 的 PlaceObject2 更新、RemoveObject、普通 DoAction 和运行时 attachMovie 均不计入直接引用。

运行：python3 tools/build_role_reference_evidence.py --crosswalk build/as2-probe/role-crosswalk.json --timeline-index build/as2-probe/timeline-index.json --output build/as2-probe/role-reference-evidence.json

CI 将输出作为纯元数据 artifact，不公开原版脚本、图像、音频或标签正文。门禁检查同源哈希、角色 ID 唯一、Sprite ID 一致、时间轴唯一、事件帧号与偏移有效。

**限制**：DoInitAction 目标不证明角色函数被执行；没有直接引用也不代表不可选或未使用。仍需恢复真实 ActionScript 调用关系、角色动作帧、碰撞箱、伤害、指令及状态转换，才能导入 HTML5。
