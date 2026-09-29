# T2B Template Rules

These four templates are intentionally independent.

## Placeholder sources
- `{{TOP_SUBCKT}}`: authoritative top `.SUBCKT` name from SPF.
- `{{RON}}`: current impedance value, e.g. `30`, `34`, `40`.
- `{{DATE_YYYY/MM}}`: generation date.
- `{{SPICE_TYPE}}`: project setting (`Spectre` or `HSPICE` etc.).
- `{{SPICE_COMMAND}}`: linked project command.
  - Spectre default: `spectre +preset=mx +spice +mt=4`
  - HSPICE default: `hspice -mt 4`
- `TEMP_*`: Config Corner temperature, order TYP/MIN/MAX.
- `VOLT_*`: selected IBIS logic/IO voltage domain (current project: VDDQ), order TYP/MIN/MAX.
- `VIH_*`: independently selected VIH voltage domain, order TYP/MIN/MAX.
- `TR_*`, `TF_*`: Config module-level corner values, order TYP/MIN/MAX.

## Model thresholds
Use the selected logic range / VDDQ values for each corner:
- `VMEAS = VDDQ / 4`
- `VINH  = VMEAS + 0.05 V`
- `VINL  = VMEAS - 0.05 V`

The ±50 mV offset is currently fixed.

## Pin mapping
SPF original pin names are mapped in Config Excel to fixed IBIS aliases.
- Single-ended: `iopad`, `txdat`, `txoe`, `vddq`, `vss`
- Differential: `ipadt`, `ipadc`, `txdat`, `txoe`, `vddq`, `vss`

If a Config original pin does not exist in the top SUBCKT, generation must fail instead of guessing.

## Model Selector
Do not generate `[Model Selector]`. `[Pin]` points directly to the actual model.

## Model file naming
Do not append module suffixes such as `_io_se`, `_io_diff`, or `_iodiff`.
Use only:
- `corner_drv_ron<RON>_{typ|min|max}.sp`
- `corner_rcv_ron<RON>_{typ|min|max}.sp`

## Fixed files
- `[Spice file] component.sp`
- `[ExtSpiceCmd] ckt_topology.sp`

## Waveforms
DRV only. Keep Golden structure fixed.
The second Rising/Falling rows reuse `VOLT_TYP/VOLT_MIN/VOLT_MAX`.
All other numeric/NA fields stay fixed as shown in the templates.
