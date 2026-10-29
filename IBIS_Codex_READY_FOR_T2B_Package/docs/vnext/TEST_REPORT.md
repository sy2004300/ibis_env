# VNext 验证记录

日期：2026-10-30（Asia/Shanghai）。基线 `c644a77`，开发分支 `codex/ibis-vnext-config`。

- Python 3.12 + Xvfb：181 项 unittest 全部通过，含旧版 GUI 和新增 VNext 真实 Tk 窗口测试，无跳过。
- 新增 VNext：17 项，通过双格式往返、GUI 工作流、8 个合成 DRV/RCV Case、完整 Pin 顺序、Excel 修改实际生效、来源 STALE、阻断矩阵、FS/SF 实际生成、超长元数据、只读输入与 Workspace 保护。
- 原有 Acceptance：FIXTURE CHECK、STRUCTURAL CHECK、GOLDEN CASE 001、FINAL READY_FOR_T2B 全部 PASS。
- Python 3.7.8 / Tk 8.6 / openpyxl 3.0.10：181 项 unittest 全部通过，无跳过；真实 Tk 编辑/生成、Acceptance/Golden 和启动 `--check` 均 PASS。使用固定 python:3.7.8 容器，依赖以离线 wheel 安装。
- GitHub Linux/Windows 构建记录与下载地址在 PR 中记录。

没有修改冻结 inputs、templates/t2b、golden、SPEC、ACCEPTANCE_TESTS、test_vectors 或 run_acceptance.py。新增 VNext Case 通过结构检查、状态 UNVALIDATED（没有相应 Golden），并非新增/替换 Golden。

未执行真实 T2B、SPICE、LSF、Stage 2 Merge，也没有生成 C_comp_view。尚需公司 CentOS 7 桌面及真实 PDK/MSI/SPF 人工验收。3.7.8 Docker 是 Debian 用户空间，Xvfb 是虚拟显示，不能替代上述验收。
