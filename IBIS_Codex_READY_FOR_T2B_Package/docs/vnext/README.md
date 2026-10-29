# IBIS Automation VNext 0.5.0

基线是已验证的 `codex/ibis-ui-0-4-2-python37`，提交 `c644a77`，包含 Python 3.7 与 Tk 命名字体兼容修复。新旧格式共用现有 Tk 应用、ProjectStore 和 Stage 1 Generator。没有修改 Stage 2 Merge、冻结输入、母模板、Golden 或 Acceptance 判断标准。

## 启动与实际操作

Python 3.7.8 使用 `openpyxl==3.0.10`、`et_xmlfile==1.1.0`。在代码根目录运行：

```bash
python3 -m pip install openpyxl==3.0.10 et_xmlfile==1.1.0
python3 start_ibis_ui.py --workspace /your/MSDV/workspace
# 原有入口仍可用
PYTHONPATH=src python3 -m ibis_ui --workspace /your/MSDV/workspace
```

1. 新建或打开项目，点击同一个“导入 Config Excel”。选择极简 Input 或正式 Generated 文件。自动读取来源并检查；不会执行 Demo Sheet 的示例。
2. 在“待填写 / 待修正”中选择问题，界面会展开对应分区、定位单元格。双击编辑，回车或移开焦点应用；稍后自动重新检查。Source 可选择目录或文件。
3. 填写真实电压、全局 Tr/Tf、Corner 和 MSI 选择。Pin 的 SPF 选项来自真实有序 `.SUBCKT`。`ipadt` 与 `IOPADT` 不同名，必须选择；修改后标记 MANUAL。来源变化后的 STALE 行须核对并点击“核对后确认映射”。删除不再适用的旧映射须由用户明确操作。
4. 可随时“保存项目”或“导出 Config Excel”，即使还有阻断项。原始导入 Excel 禁止覆盖。导出的表可离线编辑后再次 Import；可见单元格是真正配置，不是只读报告。
5. 阻断数为零才启用 Generate T2B。点击时再次检查，并保存配置后调用现有 Stage 1 Generator。生成期间可取消后续 Case；不启动真实 T2B、SPICE 或 LSF。
6. 左侧 Case 树可选择填参预览；“生成结果”中双击已有 Case 可查看文件。没有对应 Golden 的新配置显示 UNVALIDATED，表示结构通过但没有 Golden 验证，绝不伪装为 Golden PASS。

附带 `IBIS_Config_Generated_Example_Final.xlsx` 的 **Generated Demo 仅是用户提供的布局示意**。导入它会显示说明和空配置，不会使用示例中的短模块名、伪路径或状态公式。正式输出的 Sheet 是 `Config_Generated`。

## 数据与校验规则

- `config.vnext.schema_version = 1` 是新格式的唯一事实源，仍放在 Project Schema 2 中。外层旧格式字段仅供任务树显示；进入生成器前由适配器转换到 Canonical Config，绝不只在 Generator 中硬编码新字段。
- Input 按标题与列名读取，只解析 `Input`；支持插入额外 Module、Voltage、Signal 行。Ron 单元格支持逗号、空格、分号及常见中文分隔符，去重且校验实际 MSI code。
- Tr/Tf 只在全局 Corner 表中编辑。方向与拓扑推导四套模板，不提供独立 Template Mapping、Simulation Options 或 MSI Attribute Override 表。必要的原有 SPICE option 与模板命令仍保留。
- 所有必需域的 MAX/TYP/MIN 电压由用户提供，包括 VSS；软件只补域名，不编造数值。全局信号只作用于存在该信号的模块；局部非空值优先，空白继承全局/MSI。支持 Verilog b/h/d、0x、0b、十进制，并检查位宽。禁止普通覆盖改写 Ron 控制信号或 T2B 接管的 Pin。
- `[Pin]`、`->` 与 `[Diff pin]` 单独解析。只有忽略大小写后的同名才可自动匹配。检查重复节点、Pin 类型、真实 SPF Pin、五字符 ASCII 对外命名。CKT `x1` 保留完整 SPF Pin 数量、原始顺序和原 Top 名，只替换确认的对应节点。
- Model 可为根目录或完整同级库中的 `.lib` 锚点；MSI 可为目录或 `.xlsx`；SPF 可为目录或 `.spf` 锚点，但三个 Corner 必须三个独立文件且接口完全一致；单 T2B 仅支持单一方向/拓扑计划。空 T2B Source 使用内置母模板。全局 `_t2b_config.ini` 使用软件自带只读配置。
- PDK section 从真实 `.lib section` 或 Spectre `section name` 声明验证。FF/TT/SS 支持已有命名；FS/SF 仅使用真实存在且唯一的同名或库名前缀 section。其它 PDK 命名约定不会猜测，会明确阻断，需要适配规则或由工程师提供合法的库包装文件。
- MSI 候选按真实工作簿/Sheet 列出，只有唯一同名模块才自动选择；相似名称不自动确认。保留原始属性，校验 WIDTH、方向、供电域、重复信号、Ron code。
- Generated Excel 隐藏 `_VNext` 元数据保留指纹和来源。可见值优先，Excel 中修改映射视为人工操作；源 SPF/T2B/MSI 内容或路径变化会使受影响的人工映射 STALE。旧选择保留，删除模块或模板 Pin 时也不悄悄丢弃原映射。
- UI 与 CLI 共用同一个预检查；伪造保存的绿色状态不能绕过后台生成门禁。生成前后复核来源 hash，过程中变化的输出标记 FAIL。

## Workspace 与只读输入

默认工作区沿用原平台设置；公司环境优先显式传入 `--workspace` 指定 MSDV 目录。自动文件仅写入 Workspace：

```text
workspace/projects/<UUID>/
  project.json
  config/imports/<SHA256>/<原始Excel副本>
  config/Config_Generated.xlsx
  config/sources/<SHA256>/<选中的MSI、SPF、T2B副本>
  logs/precheck.json
  logs/generation.json
  READY_FOR_T2B/<module>/<drv或rcv>/<ron>ohm_ibis/
```

如果重新导入的是该项目自己的 `config/Config_Generated.xlsx`，下次保存写 `Config_Current.xlsx`，保留刚导入的来源文件。主动 Export 可以选择 Workspace 外的另存路径，但不能覆盖导入 Excel。自动输出路径拒绝位于原输入目录内或经目录链接逃逸出工作区。不创建任何软链接。

模型库 `.lib` 引用仍指向真实库，保留其相对 include 语义，不复制整个 PDK。追溯记录保存选中库的 SHA256；未递归解析/封装 PDK 内部的全部 include。跨电脑迁移后需重新指定失效来源并确认映射。

## 旧格式兼容

旧 0.4.2 Excel 会明确提示“旧版配置兼容模式”，打开原有参数/MSI Master/模板/生成界面，保留原有规则，不自动转成 VNext，不覆盖原 Excel。新建项目默认 VNext。旧项目保存格式继续可读。

冻结 SPEC 与 Golden 仍约束旧流程；本轮新增规则是版本化扩展，未更改冻结标准。VNext 的合成新配置不拿旧版 Golden 冒充验证；旧入口独立运行原 Acceptance/Golden 回归。三个 UI 版本/打包契约测试仅更新预期版本号到 0.5.0，其余原有断言保留。

## CLI 与合成演示

```bash
# 与 GUI Import 一样自动预处理；存在阻断项也保存并导出
PYTHONPATH=src python3 -m ibis_ui.vnext preprocess \
  --input /path/Input.xlsx --workspace /your/MSDV/workspace \
  --output /your/MSDV/workspace/Config_Generated.xlsx

# 再次执行同一检查，通过后才生成 Stage 1
PYTHONPATH=src python3 -m ibis_ui.vnext generate \
  --input /path/Config_Generated.xlsx --workspace /your/MSDV/workspace

# 仓库内合成演示：真实创建可解析的 MSI/SPF/section 占位库和两个 Excel
python3 tools/create_vnext_demo.py --workspace /tmp/ibis-vnext-demo
```

最后一条会生成 `vnext-synthetic-demo/Config_Input.xlsx` 和 `Config_Generated.xlsx`。前者导入后需要人工映射，后者预先填写了合成 Fixture 的明确映射，用于端到端测试。**合成库没有真实器件模型，不能用于实际仿真。** 不修改 `inputs/` 中的冻结占位文件来制造检查通过。

## 测试与环境边界

自动测试覆盖双格式同入口、额外行、人工 Excel 修改影响实际生成、空电压不编造、Pin 原顺序、STALE、源歧义、FS/SF、位宽/覆盖冲突、导出门禁分离、项目隔离、原文件 hash、不污染输入，以及真实 Tk 窗口的编辑/定位/保存/重开/生成。

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 tests/run_acceptance.py
# 图形环境或 Xvfb 下运行全部测试，含真实 Tk 操作
DISPLAY=:91 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

本地已用 Python 3.12 和真正的 Python **3.7.8 / Tk 8.6 / openpyxl 3.0.10** 执行测试。3.7.8 容器基于 Debian，不能声称已在真实 CentOS 7 公司桌面上验收；仍需该环境复核字体、DISPLAY 和真实 PDK。Xvfb 窗口测试也不等于人工视觉验收。详见 `TEST_REPORT.md`。
