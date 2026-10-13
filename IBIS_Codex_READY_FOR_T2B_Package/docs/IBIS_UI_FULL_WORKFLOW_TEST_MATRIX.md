# IBIS Automation 0.4.0 — Automated Test Matrix

| Area | Automated coverage |
|---|---|
| Schema | Schema 1 migration, Schema 2 persistence, project isolation |
| Config | Section 1-10 import/edit/export, real parser semantic round trip |
| Module | Add/rename/duplicate/delete and dependent reference maintenance |
| MSI | Multi-workbook/sheet, collisions, exclusion, hashes, edit preservation |
| Template | DRV/RCV, SE/DIFF mapping, validation, history, restore, user library |
| Generation | ProjectStore adapter, selected Case, seven files, no unselected output |
| Effective edits | Option, Alias and working-template text appear in generated files |
| Safety | Source Excel/MSI unchanged, atomic files, existing Case backup |
| Validation | Golden Case 001, UNVALIDATED, Golden mismatch, Manifest and STALE |
| Reports | CSV and TXT status export |
| Compatibility | Linux/Windows path-neutral snapshot and identical schema |
| Packaging | Native Windows onedir, resources, EXE headless check, Tk smoke |

Primary commands:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=src python tests/run_acceptance.py
PYTHONPATH=src python -m ibis_ui --check --workspace /tmp/ibis-check
```

The CI Tk smoke creates and closes a real window automatically. It is distinct
from human visual acceptance.

