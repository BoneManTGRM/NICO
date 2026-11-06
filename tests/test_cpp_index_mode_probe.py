"""Owned diagnostic observer controls; no project qualification or performance claims."""
from pathlib import Path
import os
import shutil
import subprocess
import pytest
from scripts import cpp_index_mode_probe as mode
from scripts.native_stage_counters import instrument

OWNED=Path(__file__).with_name('native_index_mode_owned')


def test_header_is_separate_pinned_v4_with_unchanged_caps():
    raw=instrument.HEADER.read_bytes();after=mode.transform_header(raw)
    assert mode.digest(raw)==mode.HEADER_BASE_SHA256
    assert mode.digest(after)==mode.HEADER_AFTER_SHA256
    assert b'NICO_STAGE_V3' in raw and b'NICO_STAGE_V4' in after
    assert b'constexpr unsigned MaxRecordBytes = 1024;' in after
    assert b'constexpr unsigned MaxRecords = 128;' in after
    assert mode.receipt()['aggregation']=='observer_thread_lane'
    assert not mode.receipt()['qualification_credit']
    assert list(mode.DISABLE_REASONS.values())==list(range(7))


@pytest.mark.parametrize('raw',[b'',b'not the header',instrument.HEADER.read_bytes()+b'changed'])
def test_bad_header_rejected(raw):
    with pytest.raises(ValueError,match='header_identity'):mode.transform_header(raw)


@pytest.mark.parametrize('name',[*mode.BASELINE,'lib/ctu.cpp','outside'])
def test_unknown_or_changed_production_source_rejected(name):
    with pytest.raises(ValueError,match='source_identity'):mode.instrument_baseline(name,b'unknown')


def test_excerpt_restoration_and_missing_anchor_fail_closed(monkeypatch):
    raw=(OWNED/'tokenlist_excerpt.cpp').read_bytes()
    monkeypatch.setitem(mode.BASELINE,'lib/tokenlist.cpp',mode.digest(raw));monkeypatch.setattr(mode,'AFTER',{})
    after=mode.instrument_baseline('lib/tokenlist.cpp',raw)
    assert mode.strip(after)==raw
    broken=raw.replace(b'mLessValid = true;',b'mLessValid = false;')
    monkeypatch.setitem(mode.BASELINE,'lib/tokenlist.cpp',mode.digest(broken))
    with pytest.raises(ValueError,match='anchor_mismatch'):mode.instrument_baseline('lib/tokenlist.cpp',broken)


@pytest.mark.parametrize('raw',[mode.BEGIN+b'incomplete',mode.END,mode.BEGIN+mode.BEGIN+mode.END])
def test_marker_errors_fail_closed(raw):
    with pytest.raises(ValueError,match='markers_invalid'):mode.strip(raw)


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    compiler=shutil.which('g++');assert compiler,'owned native compiler required'
    root=tmp_path_factory.mktemp('index-mode');raw=(OWNED/'tokenlist_excerpt.cpp').read_bytes()
    # Owned excerpt explicitly repinned only inside this fixture; production pins stay fixed.
    previous=mode.BASELINE['lib/tokenlist.cpp'];outputs=mode.AFTER
    try:
        mode.BASELINE['lib/tokenlist.cpp']=mode.digest(raw);mode.AFTER={}
        (root/'methods.cpp').write_bytes(mode.instrument_baseline('lib/tokenlist.cpp',raw))
    finally:
        mode.BASELINE['lib/tokenlist.cpp']=previous;mode.AFTER=outputs
    (root/'nico_stage_counters.h').write_bytes(mode.transform_header(instrument.HEADER.read_bytes()))
    result=subprocess.run([compiler,'-std=c++11','-O2','-pthread','-I'+str(root),'-I'+str(OWNED),
        str(root/'methods.cpp'),str(OWNED/'control.cpp'),'-o',str(root/'control')],capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr.decode()
    return root/'control'


@pytest.mark.parametrize('enabled',['0','1','invalid',''])
def test_owned_active_dense_reasons_fallback_saturation_threads_and_disabled(binary,enabled):
    result=subprocess.run([str(binary)],env={**os.environ,'NICO_CPP_STAGE_COUNTERS':enabled},capture_output=True,timeout=10)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert result.stdout==('owned_index_mode_controls=pass observer='+str(int(enabled=='1'))+'\n').encode()
    assert result.stderr==b''  # No helper performs per-event logging or sampling.


def test_maximum_fields_emit_no_partial_record(binary):
    result=subprocess.run([str(binary),'overflow'],env={**os.environ,'NICO_CPP_STAGE_COUNTERS':'1'},capture_output=True,timeout=10)
    assert result.returncode==0
    assert result.stderr==b'NICO_STAGE_V4_OVERFLOW\n'  # Fixed marker, no raw partial record.


def test_format_overflow_preserves_global_record_cap(binary):
    result=subprocess.run([str(binary),'overflow-cap'],env={**os.environ,'NICO_CPP_STAGE_COUNTERS':'1'},capture_output=True,timeout=10)
    assert result.returncode==0
    assert result.stderr==b'NICO_STAGE_V4_OVERFLOW\n'*128
