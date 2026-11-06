"""Pinned diagnostic-only index-mode insertions; no production decisions change.

Apply before the existing template subphase overlay, and strip in reverse order.
Counters describe one observer thread's lists, not global or terminal state.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

BASELINE = {
    'lib/token.cpp': '479bfa7451c7be5483195980aff7a7100481dd551e003766ab75a66124765547',
    'lib/tokenlist.cpp': '42923e2ca209f582f415be75a21e14d36341fa9b2ed862c19a81f09e394d89a1',
    'lib/templatesimplifier.cpp': '23930579ec1ce6837cc4c3de8499a81761afe220fa5f00d6965b6975c25565ba',
}
HEADER_BASE_SHA256 = '2a3a4e2351e62b21d43f1922c6ea2c06a6f0145ca10ccbc05297745aa221d71c'
HEADER_AFTER_SHA256 = 'aa28847a75d1ca89c856b030c7c84f90437dbcc72f2c4c3c64ff713061b49a1e'
AFTER = {'lib/token.cpp': '479bfa7451c7be5483195980aff7a7100481dd551e003766ab75a66124765547', 'lib/tokenlist.cpp': 'dd285957f00adf3aaa70c9e8f0400d4dee1d9e18fdb202f9c5057b96fa9d749e', 'lib/templatesimplifier.cpp': '00ca2e96d28a04af21914d986dabf0cceda550edb8919024d0ed4190e9d71b7e'}
FIELDS = ('indexed_selected', 'linear_selected', 'indexed_queries', 'fallback_queries',
          'successful_builds', 'first_disable_reason', 'peak_live_slots', 'peak_total_slots',
          'index_build_visits')
DISABLE_REASONS = {'none': 0, 'build_alloc': 1, 'append_alloc': 2, 'tombstones': 3,
                   'existing_to_angle': 4, 'non_tail_insert': 5, 'identity_or_order': 6}
BEGIN = b'/* NICO_INDEX_MODE_BEGIN */\n'
END = b'/* NICO_INDEX_MODE_END */\n'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strip(raw):
    while BEGIN in raw:
        first = raw.index(BEGIN)
        last = raw.find(END, first + len(BEGIN))
        if last < 0 or BEGIN in raw[first + len(BEGIN):last]:
            raise ValueError('index_mode_markers_invalid')
        raw = raw[:first] + raw[last + len(END):]
    if END in raw:
        raise ValueError('index_mode_markers_invalid')
    return raw


def _after(raw, anchor, statements):
    anchor = anchor.encode()
    if raw.count(anchor) != 1:
        raise ValueError('index_mode_anchor_mismatch')
    return raw.replace(anchor, anchor + BEGIN + statements.encode() + b'\n' + END)


def instrument_baseline(relative, raw):
    if relative not in BASELINE or digest(raw) != BASELINE[relative]:
        raise ValueError('index_mode_source_identity')
    result = raw
    if relative == 'lib/tokenlist.cpp':
        result = _after(result, '#include "tokenlist.h"\n', '#include "nico_stage_counters.h"')
        result = _after(result, '            for (Token* token = front; token; token = token->next()) {\n',
                        '                NicoStage::indexBuildVisit();')
        result = _after(result, '            mLessValid = true;\n',
                        '            NicoStage::indexBuilt(mLessSlots.size(), mLessTokens.size());')
        result = _after(result, '        } catch (const std::bad_alloc&) {\n',
                        '            NicoStage::indexDisable(NicoStage::IndexBuildAlloc);')
        result = _after(result, '    // Unsupported mutations permanently restore linear traversal for this list.\n',
                        '    if (mLessValid) NicoStage::indexDisable(NicoStage::IndexIdentityOrOrder);')
        # Preserve the original unbraced condition and statement byte-for-byte.
        # Added braces/counter are wholly delimited and stripped for restoration.
        result = _after(result, '        if (mLessTokens.size() - mLessSlots.size() > mLessSlots.size())\n',
                        '        {\n            NicoStage::indexDisable(NicoStage::IndexTombstones);')
        anchor = b'            invalidateLessTokens();\n    }\n}\n\nvoid TokensFrontBack::changedLessToken'
        if result.count(anchor) != 1:
            raise ValueError('index_mode_anchor_mismatch')
        result = result.replace(anchor, b'            invalidateLessTokens();\n' + BEGIN + b'        }\n' + END + b'    }\n}\n\nvoid TokensFrontBack::changedLessToken')
        result = _after(result, "        // An existing token became '<'. Its lexical position is not cached.\n",
                        '        NicoStage::indexDisable(NicoStage::IndexExistingToAngle);')
        result = _after(result, '    if (token != back) {\n',
                        '        NicoStage::indexDisable(NicoStage::IndexNonTailInsert);')
        result = _after(result, '        mLessTokens.push_back(token);\n',
                        '        NicoStage::indexSlots(mLessSlots.size(), mLessTokens.size());')
        result = _after(result, '        // Index allocation must not turn a successful token edit into failure.\n',
                        '        NicoStage::indexDisable(NicoStage::IndexAppendAlloc);')
    elif relative == 'lib/templatesimplifier.cpp':
        result = _after(result, '#include "templatesimplifier.h"\n', '#include "nico_stage_counters.h"')
        result = _after(result, '    const std::vector<Token*>* lessTokens = mTokenList.lessTokens();\n',
                        '    NicoStage::indexQuery(lessTokens != nullptr);')
        result = _after(result, '            nameTok = (*lessTokens)[lessCursor++]->previous();\n            if (!nameTok)\n                continue;\n',
                        '            NicoStage::indexSelected(true);')
        result = _after(result, '            nameTok = linearNext;\n            if (!nameTok)\n                break;\n',
                        '            NicoStage::indexSelected(false);')
    if strip(result) != raw:
        raise ValueError('index_mode_restoration_failed')
    if AFTER and digest(result) != AFTER[relative]:
        raise ValueError('index_mode_output_identity')
    return result


HEADER_HELPERS = r'''
// Fixed diagnostic reasons. The first actual disable is sticky per observer lane.
enum IndexDisableReason : unsigned { IndexNone, IndexBuildAlloc, IndexAppendAlloc,
    IndexTombstones, IndexExistingToAngle, IndexNonTailInsert, IndexIdentityOrOrder };
inline void indexQuery(bool indexed) noexcept {
    if (!enabled()) return;
    increment(state().v[indexed ? IndexedQueries : FallbackQueries]);
}
inline void indexSelected(bool indexed) noexcept {
    if (!enabled()) return;
    increment(state().v[indexed ? IndexedSelected : LinearSelected]);
}
inline void indexBuildVisit() noexcept {
    if (!enabled()) return;
    increment(state().v[IndexBuildVisits]);
}
inline void indexDisable(IndexDisableReason reason) noexcept {
    if (!enabled()) return;
    if (!state().v[FirstDisableReason]) state().v[FirstDisableReason] = reason;
}
inline void indexSlots(std::uint64_t live, std::uint64_t total) noexcept {
    if (!enabled()) return;
    State& s = state();
    if (live > s.v[PeakLiveSlots]) s.v[PeakLiveSlots] = live;
    if (total > s.v[PeakTotalSlots]) s.v[PeakTotalSlots] = total;
}
inline void indexBuilt(std::uint64_t live, std::uint64_t total) noexcept {
    if (!enabled()) return;
    increment(state().v[SuccessfulBuilds]);
    indexSlots(live, total);
}
'''


def transform_header(raw):
    if digest(raw) != HEADER_BASE_SHA256:
        raise ValueError('index_mode_header_identity')
    anchor = b'UnattributedNs, OutsideNs, ObserverNs, IntervalNs, IntervalKind, Count'
    if raw.count(anchor) != 1 or raw.count(b'NICO_STAGE_V3') != 1:
        raise ValueError('index_mode_header_anchor')
    result = raw.replace(anchor, b'UnattributedNs, OutsideNs, ObserverNs, IntervalNs, IntervalKind,\n'
                         b'    IndexedSelected, LinearSelected, IndexedQueries, FallbackQueries,\n'
                         b'    SuccessfulBuilds, FirstDisableReason, PeakLiveSlots, PeakTotalSlots, IndexBuildVisits, Count')
    result = result.replace(b'NICO_STAGE_V3', b'NICO_STAGE_V4')
    # Keep the same accepted record slot and byte cap, but make formatting loss
    # explicit so a retained earlier prefix cannot be mistaken for complete data.
    result = result.replace(b'    endCheckpoint(checkpoint);',
        b'    else {\n'
        b'        static const char overflow[] = "NICO_STAGE_V4_OVERFLOW\\n";\n'
        b'        (void)std::fwrite(overflow, 1, sizeof(overflow) - 1, stderr);\n'
        b'        (void)std::fflush(stderr);\n'
        b'    }\n'
        b'    endCheckpoint(checkpoint);')
    result = result.replace(b'} // namespace NicoStage\n', HEADER_HELPERS.encode() + b'} // namespace NicoStage\n')
    if HEADER_AFTER_SHA256 != 'PENDING' and digest(result) != HEADER_AFTER_SHA256:
        raise ValueError('index_mode_header_output')
    return result


def receipt():
    return {'schema': 'nico.cpp-index-mode-overlay.v1', 'source_sha256': BASELINE,
            'instrumented_source_sha256': AFTER, 'restored_source_sha256': BASELINE,
            'base_header_sha256': HEADER_BASE_SHA256, 'header_sha256': HEADER_AFTER_SHA256,
            'script_sha256': digest(Path(__file__).read_bytes()), 'fields': list(FIELDS),
            'disable_reasons': DISABLE_REASONS, 'aggregation': 'observer_thread_lane',
            'query_unit': 'replacement_function_entry', 'selected_unit': 'nonnull_candidate_token',
            'instrumentation_only': True, 'qualification_credit': False}
