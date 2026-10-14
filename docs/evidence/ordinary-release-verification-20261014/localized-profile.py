import cProfile, pstats
from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status, _pdf_observation
s = _fixed_status('en')
p = cProfile.Profile()
p.enable()
r = _pdf_observation(s, 'es-MX')
p.disable()
print(r)
pstats.Stats(p).strip_dirs().sort_stats('cumulative').print_stats(35)
