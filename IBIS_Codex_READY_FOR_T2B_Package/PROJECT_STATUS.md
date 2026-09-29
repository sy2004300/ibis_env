# PROJECT_STATUS

## 已冻结

- READY_FOR_T2B 前的主流程与大部分判断分支
- Config Excel v1 schema
- Synthetic 35-pin Demo MSI/SPF
- Case 输出目录结构：`generated/<Module>/<drv|rcv>/<XX>ohm_ibis/`
- Case 001：`demo_phy_io_diff / DRV / drv_diff / 30Ω`
- `_t2b_config.ini` 为全局唯一静态输入，每个 Case 复制一份
- `C_comp_view` 属于 T2B 运行后输出，不在 READY_FOR_T2B 输入中生成

## 当前只有一套 Golden

`drv_diff + 30Ω`。

因此：

- 有 Golden 且通过：`PASS`
- 没有 Golden，但结构检查通过：`UNVALIDATED`
- 有 Golden 但不一致，或结构检查失败：`FAIL`

## 尚未完全冻结

T2B 模板内部所有项目参数的最终通用化规则尚未逐项与真实四套模板核对。

本包提供四套 synthetic template 以便 Codex 实现模板库/实例化架构，其中：

- `drv_diff.t2b`：由当前 Case 001 验证
- `drv_se.t2b` / `rcv_diff.t2b` / `rcv_se.t2b`：架构占位与分支测试用途，当前为 `UNVALIDATED`

后续拿到真实模板时应替换模板数据，不应重写整个 generator 架构。
