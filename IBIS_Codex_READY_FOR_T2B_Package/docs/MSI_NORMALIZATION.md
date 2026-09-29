# MSI_NORMALIZATION

## 常见 Header Alias

内部字段应允许识别常见命名差异，例如：

- signal_name：PIN_NAME / Pin Name / Name / *PIN NAME
- width：WIDTH / Width
- direction：DIRECTION_TYPE / I/O / Direction
- power_domain：POWER_DOMAIN / Power Domain
- ground_domain：GROUND_DOMAIN / Ground Domain
- default_value：DEFAULT_VALUE / Default Value / DEFAULT_VALUE (phy reset) / DEFAULT_VALUE (power off)
- description：DESCRIPTION / Description(internal) / Signals Description
- databook_description：DATABOOK_DESCRIPTION / Description(external)

若存在多个 PIN_NAME 候选列，不允许自动选择错误项目列；要求显式选择。

## Impedance Map

优先尝试从 Databook Description / Description 中抽取 `code : ohm` 对。

若两个描述列都解析到完整 map：

- 完全一致 → 接受
- 不一致 → 中文错误 `MSI_IMPEDANCE_MAP_CONFLICT`

## Default Value

建议解析为：raw / numeric / bit_width / valid。

无效：X / Z / - / blank / 无法解析文本。
