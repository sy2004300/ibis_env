# CONFIG_SCHEMA

Config 位于 `inputs/config/ibis_config.xlsx`，单 Sheet：`IBIS_Config`。

Parser 规则：

- 用 Section 标题 + Header 定位，不用固定行号。
- merged cells 只负责视觉效果。
- 新增行即使没有复制 merge 格式，也必须能被识别。
- 空白数据行忽略。

## 关键下拉值

Generate Type：`DRV / RCV / BOTH`

Corner Override：`MAX / TYP / MIN / ALL`

T2B Template Type：`drv_se / drv_diff / rcv_se / rcv_diff`

MSI Attribute Override 当前允许：`POWER_DOMAIN`

## Signal Override 冲突

只要同一 Module + Signal 的两条规则作用域有交集，就报错；完全重复也报错。

例如 `BOTH+ALL` 与 `RCV+TYP` 作用于同一 Signal → 冲突，不做“更具体优先”。
