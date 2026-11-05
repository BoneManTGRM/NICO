import time, copy
from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
from nico import comprehensive_same_run_locale_report_v1 as locale
s = _fixed_status('en')
for count in (1, 100, 1000):
    c = copy.deepcopy(s['reports']['json'])
    r = _install_finalized_scanner_register(c)
    item = r['findings'][0]
    r['findings'] = [dict(item, candidate_id=f'synthetic-{i}', finding_id=f'synthetic-{i}', evidence='Synthetic performance fixture only. ' * 30) for i in range(count)]
    r['candidate_record_count'] = count
    r['totals'] = dict(raw=count, review_required=count, source_path=count)
    started = time.monotonic()
    try:
        result = locale._render_target(c, 'es-MX')
        print(dict(count=count, seconds=round(time.monotonic()-started,3), pages=result.get('pdf_page_count'), bytes=len(result.get('pdf_base64',''))), flush=True)
    except Exception as e:
        print(dict(count=count, seconds=round(time.monotonic()-started,3), error=type(e).__name__, detail=str(e)), flush=True)
