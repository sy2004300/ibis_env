# MASTER_PROMPT — 给 Codex

你正在实现一个 IBIS READY_FOR_T2B 自动化平台的第一版。

## 目标

从本仓库冻结的 `inputs/ + templates/ + SPEC.md` 出发，从零实现 generator，最终生成 READY_FOR_T2B Case，并让 `tests/run_acceptance.py` 全部通过。

## 第一步

必须按顺序阅读：

1. `AGENTS.md`
2. `SPEC.md`
3. `ACCEPTANCE_TESTS.md`
4. `PROJECT_STATUS.md`
5. `README.md`

## 实现要求

- 使用清晰模块化架构，不写一个巨型脚本。
- 推荐内部层次：ConfigParser / MSIDiscovery+Parser / SPFIndex+Parser / CanonicalModel / CaseExpander / ComponentGenerator / TopologyGenerator / CornerGenerator / T2BTemplateRenderer / Validator / Diagnostics。
- Parser 不依赖 Excel 固定行号或 merged-cell 几何。
- 先构建 Canonical Model，再由各 generator 消费，避免多个文件各自重复解释输入。
- 保留 CLI 与未来 UI 共用的 service layer。
- 所有用户可见 Warning/Error/Summary 使用中文。

## 必须实现的命令

```bash
PYTHONPATH=src python -m ibis_auto generate \
  --config inputs/config/ibis_config.xlsx \
  --output generated \
  --non-interactive
```

若需额外 Runtime Override 参数可以增加，但不能破坏上述默认命令。

## 自主迭代

实现后执行：

```bash
python tests/run_acceptance.py
```

如果失败：

- 查看 diff / diagnostics
- 修复 `src/` 实现
- 重新运行
- 重复直到 PASS

不要修改 frozen reference material 来让测试通过。

## 当前验收目标

必须得到：

`generated/demo_phy_io_diff/drv/30ohm_ibis/`

并与 Case 001 Golden 对齐。

其它三类 T2B template 当前没有真实 Golden，应保持架构支持，但状态可视为 UNVALIDATED。

## 边界

到 `READY_FOR_T2B` 停止。不要实现真正 T2B 启动、LSF、C_comp_view/.ibs runtime validation，除非用户后续明确要求。

## 完成时输出

- 实现摘要
- 目录结构
- acceptance test 结果
- 尚未 Golden 验证的分支
- 任何 SPEC_CONFLICT（如果存在）
