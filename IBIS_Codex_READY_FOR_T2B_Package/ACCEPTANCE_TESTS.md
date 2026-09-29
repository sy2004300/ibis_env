# ACCEPTANCE_TESTS

## A. Codex 必须实现的 CLI

建议并以本包测试脚本为准：

```bash
PYTHONPATH=src python -m ibis_auto generate \
  --config inputs/config/ibis_config.xlsx \
  --output generated \
  --non-interactive
```

Runtime Root 可由 CLI 参数覆盖 Config 默认值；未覆盖时解析 Config 中相对路径。

## B. Case 001 必须生成

目录：

`generated/demo_phy_io_diff/drv/30ohm_ibis/`

文件：

- `_t2b_config.ini`
- `ckt_topology.sp`
- `component.sp`
- `corner_drv_ron30_max.sp`
- `corner_drv_ron30_typ.sp`
- `corner_drv_ron30_min.sp`
- `demo_phy_io_diff_drv_ron30.t2b`

不得提前生成 `C_comp_view`。

## C. 结构测试

必须验证：

1. SPF Top expanded pin count = 35。
2. ckt_topology wrapper pin 顺序继承 SPF。
3. Alias 至少包含：ipadt/ipadc/txdat/txoe/vddq/vss。
4. 30Ω PU/PD code 都为 `1111`。
5. Calibration 三角完整展开全部 8 bit，包括 0 bit。
6. `reg_txffe[3:0]=0000` 四个 bit 都生成。
7. DRV corner 中 VDD active；VDDQ/VSS/TXOE/TXDAT local source 被注释并集中在前面。
8. IOPADT/IOPADC 不得出现假的 local voltage source。
9. `.option method=gear` 与 `.option runlvl=5` 位于 `.unprotect` 后。
10. `component.sp` 为每个 domain 的 MAX/TYP/MIN 三参数，不包含 Simulation Option。
11. `_t2b_config.ini` 与模板库原件一致。

## D. Unit rule vectors

读取 `tests/test_vectors.json`：

- 240Ω→0001
- 120Ω→0011
- 80Ω→0101
- 60Ω→0111
- 48Ω→1001
- 40Ω→1011
- 34Ω→1101
- 30Ω→1111

这些是“多个合法 code 默认取数值较小者”的测试向量。

## E. Golden Case 001

Golden 路径：

`golden/demo_phy_io_diff/drv/30ohm_ibis/`

比较前仅允许做以下 canonical normalization：

1. CRLF→LF。
2. 去除每行末尾空白。
3. 将实际解析后的 Model Root 替换为 `{{MODEL_ROOT}}`。
4. 将实际解析后的 SPF Root 替换为 `{{SPF_ROOT}}`。

除此之外保持严格文本比较。

## F. 错误分支必须有测试

至少覆盖：

- Config 无法读取 → 项目级停止
- 模板缺失 → 项目级停止
- MSI Bus WIDTH 冲突 → Module FAIL
- SPF 0 个/多个匹配 → Module FAIL
- Calibration Signal 缺 MSI/SPF → Module FAIL
- Override 重复/作用域重叠 → Module FAIL
- Target Ron 映射缺失 → Case FAIL
- Default Value 为 X/Z/-/blank → Case FAIL，中文提示包含 Module/Signal/原始值
- bit=1 且 Power Domain 缺失 → Case FAIL
- 全0 Signal 缺 Power Domain → Warning，可继续
- MAX/TYP/MIN Process 非 FF/TT/SS 常规关系 → Warning + Continue/Abort

## G. 最终状态

当前 Demo 正常运行应至少得到：

- Case 001：PASS
- 其它未触发模板：不要求产生 Case
- 项目最终：READY_FOR_T2B
