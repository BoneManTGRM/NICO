from nico.cli import scan_text

class AppSecScanner:
    name = 'built_in_appsec_scanner'
    def scan_file(self, context):
        excluded = {'secret_exposure', 'dependency_risk', 'log_anomaly', 'identity_risk'}
        return [f for f in scan_text(context.relative_path, context.text) if f.get('category') not in excluded]
