"""Architecture audit regression tests."""
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'utilities'))
from architecture_audit import CodeAudit


def test_architecture_audit_clean():
    """Ensure no duplicate methods or context-manager abuses remain."""
    workspace_root = Path(__file__).resolve().parents[1]
    audit = CodeAudit(workspace_root)

    audit.scan_python_files()
    duplicates = audit.report_duplicates()
    context_abuse = audit.report_context_manager_abuse()

    assert not duplicates, "Duplicate methods detected by architecture audit"
    assert not context_abuse, "Context-manager abuse detected by architecture audit"
