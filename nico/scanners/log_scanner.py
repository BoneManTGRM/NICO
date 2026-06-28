from nico.cli import scan_text

class LogScanner:
    name = 'built_in_log_scanner'
    def scan_file(self, context):
        return [f for f in scan_text(context.relative_path, context.text) if f.get('category') in {'log_anomaly', 'identity_risk'}]
