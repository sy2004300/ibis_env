# VNext 0.5.1 Windows 实测修复

本轮在 0.5.0（`ead0e7f`）上增量修复三个问题，仍使用 `codex/ibis-vnext-config`，原有 Stage 1 生成规则、Frozen Input、Golden 和 Stage 2 不变。

## 1. 生成文件双栏预览

双击 Case 打开预览：左侧文件列表、右侧完整文本。默认选中 `ckt_topology.sp`，然后依次列出 `component.sp`、Corner SP、T2B 和其他文件。列表与文本均可横向/纵向滚动。文本为只读等宽字体、不自动换行，保留空格、缩进和行结束符，支持 Ctrl+A / Ctrl+C。

“打开输出文件夹”在 Windows 调用系统 Explorer，在 Linux 调用 `xdg-open`，macOS 调用 `open`。系统文件管理器不可用时显示中文提示和完整目录。

复用了旧版双栏方案并抽成 `src/ibis_ui/file_preview.py`，旧版和 VNext 都调用同一组件。

## 2. Signal Code

Global Signal Defaults 与模块/方向级 Signal Override 使用同一编辑机制：

| Signal | 位宽（来自 MSI，只读） | 进制 | MAX 代码值 | TYP 代码值 | MIN 代码值 |
|---|---|---|---|---|---|
| reg_txffe[3:0] | 4 | 二进制 | 1111 | 1111 | 1111 |

- 新增空行默认二进制，填写纯代码值即可。切换到十六进制显示 `F`，切到十进制显示 `15`，数值始终为 15。进入 Canonical Config 后分别转换为 `4'b1111`、`4'hF`、`4'd15`；Generator 不猜测进制。
- 旧数据里的裸数字仍按旧规则视为十进制。例如旧值 `10` 转二进制显示 `1010`，不会被重新解释为 2。旧的 `1111` 如果超出 4-bit，不会被默认进制悄悄修正；请先清空该非法值，选择二进制后重新填写。
- 旧 Verilog b/h/d、0b、0x 仍可导入或粘贴。标准单引号与常见智能单引号兼容；其他非法引号明确报错。MAX/TYP/MIN 不同旧格式按实际数值统一到本行进制。
- 即时检查格式和 MSI 位宽，4-bit 十六进制 `1F` 阻断生成。非法配置仍可保存/导出。切换进制遇到非法值会拒绝转换，保留原值以便修正。
- MSI Default 与 Config Override 使用相同的逻辑值解析器；Override 转成完整字面量后再传给 Core，不把二进制数字串重复当十进制处理。不会修改原 MSI。
- UI 和 Excel 的位宽显示均取自实际 MSI；手动篡改 Excel 的位宽列不会改变生成使用的位宽。

新 Input 模板：`IBIS_Config_Input_0_5_1.xlsx`。原 `IBIS_Config_Input_Final.xlsx` 保留为旧格式兼容输入。两者仍使用同一个 Import Excel。

完整 Excel 的 Section 3 与 Signal Override 增加中文“位宽”“进制”列，代码值写为文本以保留前导零，进制有下拉选项。为了兼容已有离线编辑习惯，原 MAX/TYP/MIN 列位置保留，新增两列放在后面。导出再导入保留数值和进制。完整 Generated 表只修改进制、未改代码值时，回导会根据隐藏元数据转换未改动单元格，保持原数值；同时改写的代码值按新进制读取。Excel 本身不运行宏，显示转换在回导时完成。

新 VNext 内部/Excel 格式标记为 **schema_version 2**（外层 Project Schema 仍为 2）。0.5.1 兼容读取 VNext schema 1；旧文件不会被自动覆盖。0.5.0 会拒绝打开新 schema，避免旧软件把新的纯二进制数字串误当十进制。回退使用旧软件时请保留原 0.5.0 项目/Excel。

## 3. CKT Append

检查器按当前 Module/Direction 获取完整 SPF Pin List，并仅应用状态为 MANUAL/AUTO_MATCH 的已确认映射，再检查追加电路节点。

`ipadc → IOPADC` 确认后，`Res ipadc vss r=100` 不再误报警。DRV/RCV 分别计算映射；UNRESOLVED、STALE 映射和真实不存在的节点仍提示。实际生成 `x1` 的完整 Pin 数量、顺序和 Top 名称保持不变，追加语句原样保留。

## 验证

新增回归覆盖：三进制等值的实际六 Case 赋值；进制切换和旧数据语义；Excel Input/Generated 往返；智能引号和 MSI Default/Override 双链路；4-bit 溢出；有效映射后的 Append；未确认/STALE/未知节点；完整 x1 顺序；真实 Tk 双栏预览、复制、字段编辑和生成门禁。

测试命令：

```bash
DISPLAY=:91 PYTHONPATH=src python -m unittest discover -s tests -v
python tests/run_acceptance.py
```

继续验证 Python 3.7.8 / openpyxl 3.0.10 与 Windows 原生 PyInstaller EXE。Windows Explorer 交互、真实 CentOS 7 桌面和真实工程仿真仍需用户本机验收；自动化不会运行实际 T2B/LSF。
