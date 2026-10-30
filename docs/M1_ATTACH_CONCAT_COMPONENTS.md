# M1: attachMovie 拼接参数分量证据

本轮扩展 `build_attach_argument_provenance.py`，对已验证 FFDec AS2 导出中 `attachMovie` 的首参数进行**顶层加号分量**词法分析。字符串内、括号内的加号不拆分；自增、复合运算符不当作简单拼接。输出每个分量的顺序、语法类别、哈希及候选前置赋值。仅允许 SWF ExportAssets 已有名称明文出现，未知字面量与变量名只输出 SHA-256。

运行入口沿用 `.github/workflows/m1-as2-export-probe.yml`，报告仍写入 `build/as2-probe/attach-argument-provenance.json`，只上传元数据，不公开原始 AS2、图像、音频或 SWF 导出字节。工作流对拼接事件增加分量数量门禁，单元测试覆盖嵌套括号、字符串内加号、已知/未知字面量、标识符赋值及自增操作。

**证据边界**：这些分量不是已求值的最终字符串；即使某个分量匹配 ExportAssets，也不代表最终参数指向该资源，更不能证明角色创建、动作帧或碰撞箱已经恢复。下一步结合真实 artifact 中分量类型和调用上下文继续追踪数据流，保持未确认项为未知。
