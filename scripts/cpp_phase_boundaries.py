"""Local-only diagnostic overlay: no execution, download or qualification wiring."""
import hashlib
PIN='76beaa920046dbe057c5b20b09c043802351692657e2b3f269cf4612984eac88'
BEGIN=b'/* NICO_PHASE_BOUNDARY_BEGIN */\n'
END=b'/* NICO_PHASE_BOUNDARY_END */\n'

def strip(raw):
    while BEGIN in raw:
        start=raw.index(BEGIN); end=raw.index(END,start)+len(END)
        raw=raw[:start]+raw[end:]
    return raw

def overlay(raw):
    if hashlib.sha256(raw).hexdigest()!=PIN: raise ValueError('source_identity_mismatch')
    original=raw
    anchors=[
      (b'#include "tokenize.h"\n', b'''namespace {
void nicoPhaseBoundary(const char* phase) {
    static std::atomic<unsigned> emitted{0};
    unsigned count = emitted.load();
    while (count < 16) {
        if (emitted.compare_exchange_weak(count, count + 1)) {
            std::fputs(phase, stderr);
            std::fflush(stderr);
            return;
        }
    }
}
}
'''),
    ]
    # stdio header is inserted before the helper; constant strings only.
    anchors[0]=(anchors[0][0],b'#include <cstdio>\n#include <atomic>\n'+anchors[0][1])
    anchors.extend([
      (b'    // using A = B;\n', b'    nicoPhaseBoundary("NICO_PHASE_V1 using_begin\\n");\n'),
      (b'    while (simplifyUsing())\n        ;\n', b'    nicoPhaseBoundary("NICO_PHASE_V1 using_end\\n");\n'),
      (b'        // Handle templates..\n', b'        nicoPhaseBoundary("NICO_PHASE_V1 template_begin\\n");\n'),
      (b'            simplifyTemplates();\n        });\n', b'        nicoPhaseBoundary("NICO_PHASE_V1 template_end\\n");\n'),
    ])
    for anchor,addition in anchors:
        if raw.count(anchor)!=1: raise ValueError('anchor_mismatch')
        raw=raw.replace(anchor,anchor+BEGIN+addition+END)
    if strip(raw)!=original: raise ValueError('semantic_source_changed')
    return raw


def apply_to_source(source):
    """Build-only: instrument a disposable trusted-tool copy and bind restoration."""
    from pathlib import Path
    import json
    source=Path(source)
    path=source/'lib/tokenize.cpp'
    if path.is_symlink() or source.is_symlink(): raise ValueError('source_symlink')
    raw=path.read_bytes(); changed=overlay(raw)
    path.write_bytes(changed)
    return {'schema':'nico.cpp-phase-overlay.v1', 'source_sha256':PIN,
            'instrumented_source_sha256':hashlib.sha256(changed).hexdigest(),
            'restored_source_sha256':hashlib.sha256(strip(changed)).hexdigest(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'instrumentation_only':True, 'qualification_credit':False}


def parse_markers(raw):
    """Complete, unique first-cycle boundaries only; uncertainty is explicit."""
    vocabulary=('using_begin','using_end','template_begin','template_end')
    unknown={'state':'unavailable', 'last_boundary':None, 'precise_hotspot_known':False}
    if not isinstance(raw,bytes) or len(raw)>65536: return unknown
    markers=[]
    for line in raw.splitlines(keepends=True):
        if not line.startswith(b'NICO_PHASE_V1'): continue
        if not line.endswith(b'\n'): return dict(unknown,state='invalid')
        text=line.rstrip(b'\r\n')
        if not text.startswith(b'NICO_PHASE_V1 '): return dict(unknown,state='invalid')
        try: name=text[len(b'NICO_PHASE_V1 '):].decode('ascii')
        except UnicodeDecodeError: return dict(unknown,state='invalid')
        if name not in vocabulary: return dict(unknown,state='invalid')
        markers.append(name)
    if not markers: return unknown
    if len(markers)>=16: return dict(unknown,state='capped')
    if len(markers)>4 or tuple(markers)!=vocabulary[:len(markers)]:
        return dict(unknown,state='invalid')
    return {'state':'observed', 'last_boundary':markers[-1], 'precise_hotspot_known':False}


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--source',required=True)
    print(json.dumps(apply_to_source(p.parse_args().source),sort_keys=True))
