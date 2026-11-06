"""Local-only diagnostic overlay: no execution, download or qualification wiring."""
import hashlib
PIN='76beaa920046dbe057c5b20b09c043802351692657e2b3f269cf4612984eac88'
BEGIN=b'/* NICO_PHASE_BOUNDARY_BEGIN */\n'
END=b'/* NICO_PHASE_BOUNDARY_END */\n'
BOUNDARIES=('using_begin','using_end','template_begin','template_end',
            'tokens_simplified','parsed_membership_end','normal_checks_begin','normal_checks_end')

def strip(raw):
    while BEGIN in raw:
        start=raw.index(BEGIN); end=raw.index(END,start)+len(END)
        raw=raw[:start]+raw[end:]
    return raw

def overlay(raw):
    if hashlib.sha256(raw).hexdigest()!=PIN: raise ValueError('source_identity_mismatch')
    return _insert_boundaries(raw)


def overlay_subphases(raw):
    # Exact output of the separately pinned baseline subphase instrumentation.
    if hashlib.sha256(raw).hexdigest() != '0ad11c73e55a130a3e9eb660b807353527f065d6eae58564546f00852d594c5e':
        raise ValueError('subphase_source_identity_mismatch')
    return _insert_boundaries(raw)


def _insert_boundaries(raw):
    original=raw
    anchors=[
      (b'#include "tokenize.h"\n', b'''void nicoPhaseBoundary(const char* phase) {
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
    vocabulary=BOUNDARIES
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
    if len(markers)>len(vocabulary) or tuple(markers)!=vocabulary[:len(markers)]:
        return dict(unknown,state='invalid')
    return {'state':'observed', 'last_boundary':markers[-1], 'precise_hotspot_known':False}


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--source',required=True)
    print(json.dumps(apply_to_source(p.parse_args().source),sort_keys=True))


def overlay_later_stages(raw):
    if hashlib.sha256(raw).hexdigest()!='377cde381b0f6b3b4ea55ec8beeea4691992628f18589e8238f344e49ba078bd':
        raise ValueError('later_stage_source_identity')
    original=raw
    anchors=[
      (b'#include "cppcheck.h"\n', b'void nicoPhaseBoundary(const char* phase);\n'),
      (b'                    nicoConfig.disposition = "simplification_failed";\n                    continue;\n                }\n',
       b'                nicoPhaseBoundary("NICO_PHASE_V1 tokens_simplified\\n");\n'),
      (b'                    nicoConfig.parsed.capture(tokenizer, nicoConfig.tokenMembershipBytes, nicoConfig.tokenMembershipEntries);\n',
       b'                if (nicoFileTrace.enabled()) nicoPhaseBoundary("NICO_PHASE_V1 parsed_membership_end\\n");\n'),
      (b'                if (nicoFileTrace.enabled()) nicoConfig.normalPassStarted = true;\n',
       b'                nicoPhaseBoundary("NICO_PHASE_V1 normal_checks_begin\\n");\n'),
      (b'                checkNormalTokens(tokenizer, analyzerInformation.get(), nicoFileTrace.enabled() ? &nicoConfig.checksComplete : nullptr);\n',
       b'                nicoPhaseBoundary("NICO_PHASE_V1 normal_checks_end\\n");\n'),
    ]
    for anchor,addition in anchors:
        if raw.count(anchor)!=1:raise ValueError('later_stage_anchor_mismatch')
        raw=raw.replace(anchor,anchor+BEGIN+addition+END)
    if strip(raw)!=original:raise ValueError('later_stage_semantic_source_changed')
    return raw
