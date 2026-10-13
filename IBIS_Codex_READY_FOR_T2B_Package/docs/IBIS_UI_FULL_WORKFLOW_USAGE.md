# IBIS Automation 0.4.0 — Windows and Linux Usage

## Windows

Download the `IBIS_Automation_Windows_Full_Workflow` GitHub Actions artifact,
extract it completely, and double-click `IBIS_Automation.exe`. Python is not
required. Keep `_internal` beside the executable.

The default writable workspace is:

`%LOCALAPPDATA%\IBIS_Automation\workspace`

The installed application directory is treated as read-only. Project JSON,
MSI Master, working templates, generated Cases, manifests and reports are
written under the workspace or another directory explicitly selected by the
user.

For a no-window installation check:

```powershell
Start-Process .\IBIS_Automation.exe -ArgumentList '--check --check-report check.json' -Wait
```

The report must show `status: PASS`, `mode: HEADLESS`, and
`full_workflow_case_status: PASS`.

## Linux

From `IBIS_Codex_READY_FOR_T2B_Package/`:

```bash
PYTHONPATH=src python3 -m ibis_ui
```

Headless verification:

```bash
PYTHONPATH=src python3 -m ibis_ui --check --workspace /tmp/ibis-check
```

Linux defaults to `~/.local/share/IBIS_Automation/workspace/`. Use
`--workspace PATH` to select another writable location.

## Engineer workflow

1. Create/open a project and import Config Excel inside it if needed.
2. Repair local Model/MSI/SPF roots and inspect inputs.
3. Edit Config Section 1-10 and save the project.
4. Optionally preview and generate MSI Master, then save.
5. Select built-in template mappings and create valid working templates.
6. Save the project, select task-tree nodes and generate selected/all Cases.
7. Inspect files, Golden differences, manifests and generation reports.

Paths imported from another computer are not silently rewritten. Repair them in
the parameter page and save explicitly.

