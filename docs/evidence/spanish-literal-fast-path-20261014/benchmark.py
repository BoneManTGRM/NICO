import json, time
from nico import comprehensive_spanish_presentation_parity_v1 as p
from tests.test_spanish_absent_literal_fast_path import legacy
texts = [('Synthetic retained diagnostic %s. ' % i) * 300 for i in range(20)]
pairs = list(p._ES_PHRASES.items())
for function in (legacy, p._safe_replace):
    started = time.perf_counter()
    for _ in range(3):
        results = []
        for text in texts:
            for source,target in sorted(pairs,key=lambda pair:len(pair[0]),reverse=True):
                text = function(text,source,target)
            results.append(text)
    elapsed = time.perf_counter()-started
    print(json.dumps({'helper':function.__name__,'seconds':elapsed,'texts':len(texts),'phrases':len(pairs),'repeats':3}))
    if function is legacy:
        expected=results
    else:
        assert results == expected
