# IBIS Automation 0.4.0 — Manual Acceptance Checklist

- [ ] Windows ZIP extracts once to `IBIS_Automation_Windows_Full_Workflow/`.
- [ ] Double-clicking `IBIS_Automation.exe` opens a readable Chinese UI.
- [ ] New/Open exist only on the project home; Config import exists in a project.
- [ ] Config Section 1-10 dialogs are editable and one Save persists all changes.
- [ ] Exported Config Excel reopens and original Config remains unchanged.
- [ ] MSI signal detail shows raw, override and effective values.
- [ ] SPF/CKT preview shows complete ordered Original and Effective pins.
- [ ] MSI Master preview, merge and explicit ambiguous mapping operate correctly.
- [ ] DRV and RCV working templates are isolated; history can be restored.
- [ ] Invalid placeholder/template cannot be saved.
- [ ] Generate Selected does not create or delete unselected Cases.
- [ ] Generate All runs without freezing the main window.
- [ ] Case file preview scrolls horizontally and vertically.
- [ ] Golden Case 001 shows PASS for the frozen Demo configuration.
- [ ] A non-Golden valid Case shows UNVALIDATED, not PASS.
- [ ] Config/template changes mark relevant old results STALE.
- [ ] CSV/TXT summaries match the Case overview.
- [ ] About shows version 0.4.0, exact Commit and Windows platform.
- [ ] Closing with unsaved changes offers save/discard/cancel.
- [ ] No real T2B, LSF, `.ibs` or `C_comp_view` is run/generated.

CI can verify window creation and automatic interaction, but final visual layout,
font appearance and native file-dialog behavior remain a human Windows check.
