"""Bounded index-mode prefixes never imply complete execution or terminal state."""
from copy import deepcopy
import pytest
from scripts.native_stage_counters import evidence as e
from scripts import cpp_template_probe as probe
from tests.test_cpp_template_probe import sparse_record, summarize


def active(**updates):
    fields=dict(indexed_queries=1,successful_builds=1,indexed_selected=17,
        replacement_visits=17,peak_live_slots=20,peak_total_slots=20,index_build_visits=200)
    fields.update(updates)
    return fields


def test_active_and_dense_counts_retain_work_units_and_prefix_limits():
    for visits in (17,1000000):
        value=summarize(sparse_record(**active(indexed_selected=visits,replacement_visits=visits)))
        index=value['replacement_index']
        assert index['indexed_selected']==visits and index['linear_selected']==0
        assert index['index_build_visits']==200 and index['successful_builds']==1
        assert index['first_disable_reason']=='none_observed'
        assert index['scope']=='last_observed_lane_prefix' and index['lane']==0
        assert value['precise_termination_hotspot_known'] is False
        assert probe.valid_summary(value)


@pytest.mark.parametrize('reason',range(1,7))
def test_all_fixed_disable_reasons_and_linear_fallback_are_allowed(reason):
    value=summarize(sparse_record(replacement_visits=5,linear_selected=5,
        fallback_queries=1,first_disable_reason=reason))
    assert value['replacement_index']['first_disable_reason']==probe.INDEX_REASONS[reason]
    assert value['replacement_index']['linear_selected']==5
    assert probe.valid_summary(value)


def test_midquery_fallback_is_not_mislabeled_as_fallback_entry():
    value=summarize(sparse_record(**active(indexed_selected=7,linear_selected=10,
        first_disable_reason=6)))
    assert value['replacement_index']['indexed_queries']==1
    assert value['replacement_index']['fallback_queries']==0
    assert value['replacement_index']['linear_selected']==10
    assert probe.valid_summary(value)


def test_no_query_is_unknown_even_if_build_was_observed():
    for fields in ({},{'successful_builds':1,'index_build_visits':200,'peak_live_slots':20,'peak_total_slots':20}):
        value=summarize(sparse_record(**fields))
        assert value['replacement_index']=={'state':'no_query_observed','scope':probe.INDEX_SCOPE}
        assert probe.valid_summary(value)


@pytest.mark.parametrize('field',probe.INDEX_COUNTS)
def test_saturated_index_counts_remain_unknown(field):
    fields=active();fields[field]=2**64-1
    if field=='indexed_selected':fields['replacement_visits']=2**64-1
    if field=='linear_selected':fields['replacement_visits']=2**64-1
    if field=='peak_live_slots':fields['peak_total_slots']=2**64-1
    value=summarize(sparse_record(**fields))
    assert value['replacement_index']=={'state':'saturated','scope':probe.INDEX_SCOPE}
    assert probe.valid_summary(value)


@pytest.mark.parametrize('fields',[
    active(first_disable_reason=7), active(indexed_selected=16), active(peak_live_slots=21),
    active(indexed_queries=0), active(index_build_visits=-1), active(index_build_visits=2**64),
])
def test_malformed_cross_fields_are_unknown(fields):
    assert summarize(sparse_record(**fields))==probe.unknown_summary('invalid')


def test_regression_and_changed_first_reason_are_unknown():
    for update in ({'indexed_selected':16,'replacement_visits':16},{'first_disable_reason':2},
                   {'successful_builds':0},{'peak_live_slots':19},{'index_build_visits':199}):
        fields=active(first_disable_reason=1)
        second={**fields,**update}
        assert summarize(sparse_record(**fields)+sparse_record(2,**second))==probe.unknown_summary('invalid')


def test_incomplete_capped_truncated_and_overflow_are_unknown():
    raw=sparse_record(**active())
    assert summarize(raw[:-1])==probe.unknown_summary('invalid')
    assert summarize(raw+b'NICO_STAGE_V4_OVERFLOW\n')==probe.unknown_summary('invalid')
    assert summarize(b'')==probe.unknown_summary()
    capped=b''.join(sparse_record(i,**active()) for i in range(1,129))
    assert summarize(capped)==probe.unknown_summary('capped')
    assert probe.summarize_prefix(raw,binary_sha256='a'*64,timed_out=True,output_truncated=True)==probe.unknown_summary('truncated')


def test_mixed_versions_cannot_establish_index_activation():
    from tests.test_native_template_subphases import sparse_record as old_record
    for raw in (old_record(),old_record()+sparse_record(2),sparse_record()+old_record(2)):
        assert summarize(raw)==probe.unknown_summary('invalid')
    assert e.parse_snapshots(old_record(),timed_out=True,binary_sha256='a'*64,expected_version=3)['schema'].endswith('.v3')


@pytest.mark.parametrize('key,bad',[('lane',True),('indexed_selected',True),('first_disable_reason','PRIVATE'),
    ('scope','all_processes'),('indexed_queries',0),('peak_live_slots',21),('linear_selected',1)])
def test_console_rejects_forged_or_overbroad_index_claims(key,bad):
    value=summarize(sparse_record(**active()));value['replacement_index'][key]=bad
    assert not probe.valid_summary(value)


def test_multiple_lanes_are_not_combined_or_recast_as_global():
    first=sparse_record(**active())
    second=sparse_record(2).replace(b' 0 200 ',b' 1 200 ',1)
    # A fresh lane has one clock sample; global record sequence is still 2.
    value=summarize(first+second)
    assert value['replacement_index']=={'state':'no_query_observed','scope':probe.INDEX_SCOPE}
    assert value['last_interval_deltas'] is None


def test_successful_rebuild_keeps_reason_without_implying_permanent_fallback():
    value=summarize(sparse_record(**active(indexed_queries=2,successful_builds=2,first_disable_reason=5)))
    index=value['replacement_index']
    assert index['first_disable_reason']=='non_tail_insert'
    assert index['first_reason_scope']==probe.INDEX_REASON_SCOPE
    assert index['indexed_queries']==2 and index['successful_builds']==2
    assert probe.valid_index_summary(index)
