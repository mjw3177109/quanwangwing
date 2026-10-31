# M1：动态 attachMovie 标识符赋值语法取证

此增量在 Actions runner 上读取 FFDec 导出的已验证 AS2 文件，以两个未解析的 attachMovie 参数标识符的 SHA-256 为目标，逐文件核对 export-index 的长度和哈希，并与完整（未截断）的词法引用元数据逐行逐类别对照。输出只包含标识符及脚本路径哈希、行号、赋值操作符、左侧语法候选类型、右侧粗分类和汇总。

运行命令：

    python3 tools/build_dynamic_attach_assignment_sites.py --scripts build/as2-probe/exports/scripts --export-index build/as2-probe/script-export-index.json --references build/as2-probe/attach-identifier-references.json --output build/as2-probe/dynamic-attach-assignment-sites.json

该审计拒绝源 SWF 哈希不符、文件长度/哈希不符、引用示例截断、行号/语法类别不一致、路径穿越及未经验证的运行时绑定声明。仅审计目标标识符所在的导出脚本；全部 7,054 个文件的完整性由前置工作流步骤验收。

**证据边界**：赋值操作符、成员访问、声明初始化、右侧表达式粗分类都不代表真实数据流、函数可达性或角色动作。注释和字符串已掩码，不能据此判断动态 attachMovie 参数值。原版 SWF、FFDec、ActionScript 正文、美术和音频不得上传公开仓库或公开 artifact。
