from nico.cli import scan_text

class SecretScanner:
    name = 'built_in_secret_scanner'
    def scan_file(self, context):
        return [f for f in scan_text(context.relative_path, context.text) if f.get('category') == 'secret_exposure']
