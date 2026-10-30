# M1：原版 SWF 脚本容器与入口帧取证

运行 `python3 tools/build_script_entry_evidence.py --manifest build/swf-analysis/swf-manifest.json --output build/swf-analysis/script-entry-evidence.json`。

工具只读原始 SWF，先校验原文件 SHA-256，再逐个核对清单中 DoAction（12）、DoInitAction（59）、DoABCDefine（72）、DoABC（82）和 FileAttributes（69）的真实解压后字节偏移、标签头及长度。输出每条脚本容器所属时间轴、零基/一基帧号、长度和 DoInitAction 的初始化目标 ID，以及 FileAttributes 的 AS3 标志位。产物不含 ActionScript、ABC 字节码、图像或音频正文。

**证据边界**：12/59 的数量是 AS1/AS2 传统动作*容器数*，不能区分 AS1 与 AS2，也不是函数数。72/82 是 ABC 容器数，不能推断 AS3 类/方法数量。AS3 标志位仅代表 SWF 声明；没有 FileAttributes 时报告 `null` 而非假定 `false`。DefineButton2 内嵌的按钮动作、运行时生成的脚本和外部加载的 SWF 不在本报告范围。若报告与原版字节或清单不一致，CI 必须失败，不得将报告当成已恢复原版行为。
