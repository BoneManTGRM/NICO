import ast
import unittest
from unittest.mock import patch
import verify

class StaticSelection(unittest.TestCase):
    def test_no_dynamic_execution_in_fixture(self):
        for path in verify.ROOT.glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ('exec', 'eval'), str(path))

    def test_changed_static_definition_rejected_before_import(self):
        original = verify.Path.read_text
        def changed(path, *args, **kwargs):
            content = original(path, *args, **kwargs)
            if path.name == 'selected_comprehensive_orchestration_contract.py':
                content += '\nINJECTED = True\n'
            return content
        with patch.object(verify.Path, 'read_text', changed):
            with self.assertRaisesRegex(ValueError, 'static_source_mismatch'):
                verify.selected('comprehensive_orchestration_contract',
                    ['EXPRESS_STAGES','COMPREHENSIVE_ONLY_STAGES','TERMINAL_STAGES','COMPREHENSIVE_STAGES'], {})
