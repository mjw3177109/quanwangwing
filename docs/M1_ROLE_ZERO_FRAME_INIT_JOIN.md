# M1：角色脚本候选与零 ShowFrame 初始化入口交叉索引

在 FFDec AS2 导出哈希验证后，将 role-reference-evidence.json 与 zero-frame-as2-class-links.json 按原版 characterId 关联。只有原版 DoInitAction 时间轴、帧号、偏移完全一致才接受关联；类路径哈希与脚本 SHA-256 都相同才标记 same_verified_class_path。

运行：python3 tools/build_role_zero_frame_init_join.py --roles build/as2-probe/role-reference-evidence.json --zero build/as2-probe/zero-frame-as2-class-links.json --output build/as2-probe/role-zero-frame-init-join.json

报告只包含原版 ID、脚本哈希、标签位置、计数，不公开脚本正文、明文路径、ExportAssets 名称、美术或音频。没有零帧关联的角色候选显式标记 false。角色候选不等于可选角色；静态初始化不等于运行时执行；不推断招式帧、碰撞箱、伤害或 1:1 复刻。
