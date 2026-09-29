# IBIS Codex READY_FOR_T2B Package

这是用于让 Codex **从零实现 IBIS READY_FOR_T2B 自动化生成器，并自行运行验收、迭代修复** 的冻结输入包。

## 当前边界

本包覆盖：

`环境初始化 → MSI/SPF/Config 解析 → Canonical Model → Case 展开 → 文件生成 → 结构检查 → READY_FOR_T2B`

暂不覆盖：

- 真正启动 T2B
- LSF/bsub 调度
- `C_comp_view` / `.ibs` 运行后结果
- ANA/IBIS 仿真校验

## Codex 最先阅读

1. `MASTER_PROMPT.md`
2. `AGENTS.md`
3. `SPEC.md`
4. `ACCEPTANCE_TESTS.md`
5. `PROJECT_STATUS.md`

## 核心输入

- `inputs/config/ibis_config.xlsx`：最终版 Config Schema + Demo Case
- `inputs/msi/demo_msi.xlsx`：Synthetic MSI，多 Sheet，可测试 MSI Catalog
- `inputs/spf/*.spf`：三套最小合法 synthetic SPF
- `inputs/models/`：仅用于文件存在性 precheck 的 synthetic model placeholders
- `templates/t2b/`：四套固定入口 T2B template + 全局 `_t2b_config.ini`

## Golden

当前只有一套已确认 Golden：

`golden/demo_phy_io_diff/drv/30ohm_ibis/`

对应：`demo_phy_io_diff + DRV + DIFF + 30Ω + MAX/TYP/MIN`。

其它模板/Case 当前应标记 `UNVALIDATED`，不是错误。

## 重要约束

Codex 可以创建/修改实现代码，但不得为了让测试通过而修改：

- `SPEC.md`
- `ACCEPTANCE_TESTS.md`
- `golden/`
- `inputs/`
- `templates/t2b/`

若发现这些冻结输入之间存在矛盾，应输出 `SPEC_CONFLICT`，而不是擅自修改标准答案。
