# VNext 验证记录

## 当前 0.5.1：Windows 实测修复（2026-10-30）

- Python 3.12 + Xvfb：194 项 unittest 全部通过，无跳过。
- 真正的 Python 3.7.8 / Tk 8.6 / openpyxl 3.0.10 + Xvfb：同套 194 项全部通过，无跳过；启动 `--check` 通过。
- Acceptance / Structural Check / Golden Case 001 / READY_FOR_T2B：PASS。
- 本轮新增 12 项回归，覆盖三进制实际赋值等价、六个 DRV/RCV Case、UI 与 Excel 进制切换、schema 1 迁移、位宽溢出、智能引号、MSI Default/Override 不同格式、有效 Append 节点和完整 x1 顺序、真实 Tk 双栏预览与复制。
- 原有 UI 版本契约仅将期望版本/包名更新到 0.5.1；合成 Input 的测试构建器解除旧合并单元格，避免 openpyxl 插行后合并范围不移动导致再次保存丢失测试值。没有改冻结测试输入或验收标准。
- Windows 原生构建与下载结果见 PR 的 CI 链接。系统 Explorer 的本机交互、真实 CentOS 7 桌面与真实工程仿真仍需用户验收。

下面保留首次 VNext 0.5.0 的历史验证记录。


日期：2026-10-30（Asia/Shanghai）。基线 `c644a77`，开发分支 `codex/ibis-vnext-config`。

- Python 3.12 + Xvfb：181 项 unittest 全部通过，含旧版 GUI 和新增 VNext 真实 Tk 窗口测试，无跳过。
- 新增 VNext：17 项，通过双格式往返、GUI 工作流、8 个合成 DRV/RCV Case、完整 Pin 顺序、Excel 修改实际生效、来源 STALE、阻断矩阵、FS/SF 实际生成、超长元数据、只读输入与 Workspace 保护。
- 原有 Acceptance：FIXTURE CHECK、STRUCTURAL CHECK、GOLDEN CASE 001、FINAL READY_FOR_T2B 全部 PASS。
- Python 3.7.8 / Tk 8.6 / openpyxl 3.0.10：181 项 unittest 全部通过，无跳过；真实 Tk 编辑/生成、Acceptance/Golden 和启动 `--check` 均 PASS。使用固定 python:3.7.8 容器，依赖以离线 wheel 安装。
- GitHub Linux/Windows 构建记录与下载地址在 PR 中记录。

没有修改冻结 inputs、templates/t2b、golden、SPEC、ACCEPTANCE_TESTS、test_vectors 或 run_acceptance.py。新增 VNext Case 通过结构检查、状态 UNVALIDATED（没有相应 Golden），并非新增/替换 Golden。

未执行真实 T2B、SPICE、LSF、Stage 2 Merge，也没有生成 C_comp_view。尚需公司 CentOS 7 桌面及真实 PDK/MSI/SPF 人工验收。3.7.8 Docker 是 Debian 用户空间，Xvfb 是虚拟显示，不能替代上述验收。
