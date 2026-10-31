# M1：FFDec 角色脚本时间轴调用候选（元数据）

此增量不再继续重复 ActionEnd 尾部分类，而是依据已完成 SHA-256 校验的 FFDec AS2 导出，对 16 个 ExportAssets 角色变体候选脚本提取 `gotoAndPlay` / `gotoAndStop` 的**词法调用位置**。

## 输入

- `script-export-index.json`：逐文件路径、大小、SHA-256，来源于 Java 8 + 仓库 FFDec 的受限导出。
- `role-crosswalk.json`：16 个 ExportAssets 角色变体 ID、哈希校验过的 AS2 脚本路径及时间轴引用。
- `exports/scripts/`：仅在 runner 上存在的原版 AS2 源文件，绝不上传。

## 输出与验收

`role-timeline-call-evidence.json` 记录每个角色候选的脚本 SHA-256、调用所在行、方法名称、参数类别（整数字面量、字符串字面量、动态/未解析）及整数帧号候选。字符串实参和源代码正文不进入 artifact。

运行：

```bash
python3 tools/build_role_timeline_call_evidence.py \
  --scripts build/as2-probe/exports/scripts \
  --export-index build/as2-probe/script-export-index.json \
  --role-crosswalk build/as2-probe/role-crosswalk.json \
  --output build/as2-probe/role-timeline-call-evidence.json
```

CI 校验来源 SHA-256、角色变体覆盖、逐文件大小/哈希及调用分类统计闭合。新增合成回归测试覆盖注释/字符串屏蔽、整数字面量、动态参数、源哈希不符、重复角色与路径。

**证据边界**：调用表达式不等于实际执行；整数参数未验证接收者 MovieClip 所属时间轴，不能据此填充招式帧表。角色 ExportAssets 符号时间轴只有一帧，也不能据此否定脚本可能操作其他嵌套实例。下一步需要结合真实接收者对象、原始 MovieClip 层级和函数调用路径，才能确定逐动作帧。
