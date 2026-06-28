from nico.cli import scan_text

class DependencyScanner:
    name = 'built_in_dependency_scanner'
    def scan_file(self, context):
        return [f for f in scan_text(context.relative_path, context.text) if f.get('category') == 'dependency_risk']
