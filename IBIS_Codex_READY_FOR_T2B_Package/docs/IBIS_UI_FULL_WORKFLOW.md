# IBIS Automation 0.4.0 — Full Workflow Design

## Scope

Version 0.4.0 completes the local READY_FOR_T2B workflow. It does not run T2B,
Spectre, HSPICE or LSF, and it does not produce `.ibs` or `C_comp_view`.

## Data ownership

| Data | Fact source |
|---|---|
| Config Section 1-10 | `ProjectDocument.config` in ProjectStore |
| Imported Config Excel | Read-only source plus SHA256 |
| Original MSI/SPF/Model | Read-only external roots |
| MSI Master | Project workspace `msi/MSI_Master.xlsx` |
| Template mapping | ProjectStore stable template IDs |
| Working templates | Project workspace `templates/working/` |
| Template history | Immutable snapshots in `templates/history/` |
| READY_FOR_T2B output | Project workspace `generated/` |
| Case state | Real Core result plus project manifest |

Schema 2 adds workflow metadata while `ProjectDocument.from_dict()` migrates
UI-1 schema 1 projects in memory. Config Excel remains independent of template
text, generation records and MSI Master metadata.

## UI-2 Config Editor

The parameter page exposes Project/Path, Module/Direction/Ron, Process,
Temperature, Voltage Domain, Calibration and SPF Match. Ordered table dialogs
edit Simulation Option, Pin Mapping, CKT Append, Signal Override, MSI Attribute
Override and MSI Mapping. Module rename, duplicate and delete update dependent
references. Deleting a referenced voltage domain is rejected.

`Export Config Excel` writes a new workbook. The source workbook is never
overwritten. The exporter immediately calls the real `parse_config()` and
compares the Section 1-10 canonical meaning before reporting success.

## MSI Master Merge

The merge scanner recursively reads `.xlsx` files, rejects non-MSI sheets and
never treats `MSI_Master.xlsx` as a source. It creates uniquely named sheets,
`_MSI_Mapping` and `_Source_Info`. Source hashes are checked again before the
atomic replace. Existing supported `POWER_DOMAIN` and default-value edits are
preserved when the Master is refreshed. Ambiguous Module mappings require an
explicit user selection.

After merge, both ProjectStore Section 10 and Core generation point to the same
Master workbook. Original MSI workbooks remain unchanged.

## UI-3 Working Templates

Built-in `drv_se`, `drv_diff`, `rcv_se` and `rcv_diff` templates remain
read-only. A project working template is keyed by Project ID, Module and
Direction; all Ron cases for that direction share it. Saving validates required
sections, supported placeholders, Spice type and Direction/Topology. Each save
creates an immutable version snapshot. Users can restore history, restore the
built-in source, or save a snapshot to the project user library.

`_t2b_config.ini` is previewed separately and is never modified by editing a
working `.t2b` file.

## ProjectStore to Core adapter

`payload_to_core_config()` converts the saved ProjectStore payload to the same
`ibis_auto.model.Config` used by the CLI. `generate_from_config()` is the common
generation entry. The original Excel CLI calls `parse_config()` and then this
same function, so GUI and CLI do not have separate generation rules.

## UI-4 Generation

The task tree expands a selected IO Top, Direction or Ron to exact Case keys.
Generation runs on a background worker. Each Case is generated under
`.staging`, structurally validated, and atomically committed. Existing output is
backed up before replacement. Unselected Case directories are untouched.

Every completed output contains the seven Core files. Golden comparison is
performed when a Golden exists. A structurally valid Case with no Golden is
`UNVALIDATED`; a Golden mismatch is `FAIL` and remains available for inspection.

## Generated-file validation and STALE

The checker displays real `PASS`, `UNVALIDATED`, `FAIL`, `STALE` or
`NOT_GENERATED` state. Case manifests record Project ID, generator version,
commit, per-Case Config hash, template hash, source hashes, output hashes,
generation time and validation result. Relevant Config, working template or
input changes alter the fingerprint and mark the Case `STALE`.

CSV and text summaries are generated from these real records. Golden files are
never created or changed by the UI.

