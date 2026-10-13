// Opt-in diagnostic instrumentation. No analyzer decisions depend on these values.
#ifndef NICO_STAGE_COUNTERS_H
#define NICO_STAGE_COUNTERS_H
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <limits>
#include <exception>
#include <cerrno>
#include <time.h>

namespace NicoStage {
enum Field : unsigned {
    Phase, Pass, Call, Alias, OuterVisits, InnerVisits, ScopeNodes, MatchCalls,
    BaseQueries, BaseVisits, ScopeQueries, ChildVisits, Replacements, Instantiations,
    UsingCalls, Aliases, RhsDistanceCalls, RhsDistanceTokens, RhsParses, PreludeVisits,
    StableSelectionNs, StableMatchingNs, StableExpansionNs, StableReplacementNs,
    SelectionEntered, MatchingEntered, ExpansionEntered, ReplacementEntered,
    SelectionCompleted, MatchingCompleted, ExpansionCompleted, ReplacementCompleted,
    SelectionVisits, SpecializationVisits, SpecializationTokenVisits,
    ExpansionOuterVisits, ExpansionBodyVisits, ReplacementVisits, ReplacementNestedVisits,
    ActiveBucket, BucketDepth, ThreadClockStatus,
    TransitionId, TransitionSaturated, ClockReads,
    UnattributedNs, OutsideNs, ObserverNs, IntervalNs, IntervalKind, Count
};
constexpr unsigned SampleOperations = 4096;
constexpr unsigned MaxRecords = 128;
constexpr unsigned MaxRecordBytes = 1024;
constexpr unsigned IntervalMilliseconds = 1000;
inline bool enabled() {
    static const bool value = [] {
        const char* v = std::getenv("NICO_CPP_STAGE_COUNTERS");
        return v && v[0] == '1' && v[1] == '\0';
    }();
    return value;
}
struct State {
    std::uint64_t v[Count] = {};
    unsigned operations = 0;
    std::uint64_t lastThreadNs = 0, lastPostNs = 0, baselineTransition = 0, baselineBucket = 0;
    bool baselineValid = false;
};
inline State& state() { static thread_local State value; return value; }
inline unsigned lane() {
    static std::atomic<unsigned> next{0};
    static thread_local const unsigned id = next.fetch_add(1, std::memory_order_relaxed);
    return id;
}
struct Output {
    std::atomic_flag busy = ATOMIC_FLAG_INIT;
    unsigned records = 0;
    unsigned firstEntries = 0;
    std::chrono::steady_clock::time_point last{};
    const std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
};
// Function-local statics in these inline functions are shared across translation units.
inline Output& output() { static Output value; return value; }
inline void increment(std::uint64_t& v) {
    if (v != std::numeric_limits<std::uint64_t>::max()) ++v;
}
// Bucket 0=inactive, 1=selection remainder, 2=matching, 3=expansion, 4=replacement.
// Clock status 0=not attempted, 1=available, 2=unavailable (sticky).
inline void addSaturated(std::uint64_t& value, std::uint64_t amount) noexcept {
    const auto max = std::numeric_limits<std::uint64_t>::max();
    value = amount > max - value ? max : value + amount;
}
inline bool threadNow(std::uint64_t& ns) noexcept {
#ifdef NICO_STAGE_TEST_CLOCK
    return NICO_STAGE_TEST_CLOCK(ns);
#elif defined(CLOCK_THREAD_CPUTIME_ID)
    struct timespec ts;
    const int savedErrno = errno;
    const int result = clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    errno = savedErrno;
    if (result != 0 || ts.tv_sec < 0 ||
        ts.tv_nsec < 0 || ts.tv_nsec >= 1000000000) return false;
    const auto seconds = static_cast<std::uint64_t>(ts.tv_sec);
    if (seconds > (std::numeric_limits<std::uint64_t>::max() - ts.tv_nsec) / 1000000000) return false;
    ns = seconds * 1000000000 + static_cast<std::uint64_t>(ts.tv_nsec);
    return true;
#else
    (void)ns;
    return false;
#endif
}
// Called only by accepted checkpoints, never by scope guards or visits.
inline bool readThread(std::uint64_t& now) noexcept {
    State& s = state();
    if (s.v[ThreadClockStatus] == 2) return false;
    increment(s.v[ClockReads]);
    if (!threadNow(now) || (s.v[ThreadClockStatus] == 1 && now < s.lastThreadNs)) {
        s.v[ThreadClockStatus] = 2;
        s.baselineValid = false;
        return false;
    }
    s.lastThreadNs = now;
    s.v[ThreadClockStatus] = 1;
    return true;
}
inline void transition() noexcept {
    State& s = state();
    increment(s.v[TransitionId]);
    if (s.v[TransitionId] == std::numeric_limits<std::uint64_t>::max())
        s.v[TransitionSaturated] = 1;
}
struct Checkpoint {
    std::uint64_t pre = 0, transitionId = 0, bucket = 0;
    bool valid = false;
};
// Interval kind: 0=prefix, 1..4=unchanged bucket, 5=mixed/saturated,
// 6=outside measured scopes, 7=clock unavailable. Prefix/tail remain unknown.
inline Checkpoint beginCheckpoint() noexcept {
    State& s = state();
    Checkpoint c;
    c.transitionId = s.v[TransitionId]; c.bucket = s.v[ActiveBucket];
    c.valid = readThread(c.pre);
    s.v[IntervalNs] = 0;
    s.v[IntervalKind] = c.valid ? 0 : 7;
    if (c.valid && s.baselineValid) {
        const auto delta = c.pre - s.lastPostNs;
        s.v[IntervalNs] = delta;
        if (!s.v[TransitionSaturated] && c.transitionId == s.baselineTransition && c.bucket == s.baselineBucket) {
            s.v[IntervalKind] = c.bucket ? c.bucket : 6;
            addSaturated(s.v[c.bucket ? StableSelectionNs + c.bucket - 1 : OutsideNs], delta);
        } else {
            s.v[IntervalKind] = 5;
            addSaturated(s.v[UnattributedNs], delta);
        }
    }
    return c;
}
inline void endCheckpoint(const Checkpoint& c) noexcept {
    State& s = state();
    std::uint64_t post = 0;
    if (!c.valid || !readThread(post)) { s.baselineValid = false; return; }
    addSaturated(s.v[ObserverNs], post - c.pre);
    s.lastPostNs = post;
    // A reentrant transition during checkpoint processing invalidates attribution.
    s.baselineValid = c.transitionId == s.v[TransitionId] && c.bucket == s.v[ActiveBucket];
    s.baselineTransition = s.v[TransitionId]; s.baselineBucket = s.v[ActiveBucket];
}
class TemplateScope {
    unsigned bucket;
    std::uint64_t previous = 0, depth = 0;
public:
    explicit TemplateScope(unsigned value) noexcept : bucket(value) {
        if (!enabled()) return;
        State& s = state();
        transition();
        previous = s.v[ActiveBucket]; depth = s.v[BucketDepth];
        s.v[ActiveBucket] = bucket;
        increment(s.v[BucketDepth]);
        increment(s.v[SelectionEntered + bucket - 1]);
    }
    ~TemplateScope() noexcept {
        if (!enabled()) return;
        State& s = state();
        transition();
        if (!std::uncaught_exception())
            increment(s.v[SelectionCompleted + bucket - 1]);
        s.v[ActiveBucket] = previous; s.v[BucketDepth] = depth;
    }
    TemplateScope(const TemplateScope&) = delete;
    TemplateScope& operator=(const TemplateScope&) = delete;
};
inline void emit(unsigned event, unsigned kind) {
    if (!enabled()) return;
    Output& o = output();
    if (o.busy.test_and_set(std::memory_order_acquire)) return;
    const auto now = std::chrono::steady_clock::now();
    const unsigned bit = event == 1 ? (1U << kind) : 0;
    // At most three first-entry records bypass the global one-second limit.
    const bool first = bit && !(o.firstEntries & bit);
    if (o.records >= MaxRecords || (!first && o.records &&
        now - o.last < std::chrono::milliseconds(IntervalMilliseconds))) {
        o.busy.clear(std::memory_order_release);
        return;
    }
    o.firstEntries |= bit;
    o.last = now;
    ++o.records;
    const Checkpoint checkpoint = beginCheckpoint();
    char line[MaxRecordBytes];
    const auto wall = std::chrono::duration_cast<std::chrono::microseconds>(now - o.start).count();
    const std::clock_t cpu = std::clock();
    int size = std::snprintf(line, sizeof(line), "NICO_STAGE_V3 %u %u %u %u %llu %lld %llu",
        o.records, event, kind, lane(), static_cast<unsigned long long>(wall),
        static_cast<long long>(cpu), static_cast<unsigned long long>(CLOCKS_PER_SEC));
    for (unsigned i = 0; i < Count && size > 0 && size < static_cast<int>(sizeof(line)) - 1; ++i) {
        const int n = std::snprintf(line + size, sizeof(line) - size, " %llu",
            static_cast<unsigned long long>(state().v[i]));
        if (n < 0 || n >= static_cast<int>(sizeof(line)) - size) { size = -1; break; }
        size += n;
    }
    if (size > 0 && size < static_cast<int>(sizeof(line)) - 1) {
        line[size++] = '\n';
        (void)std::fwrite(line, 1, static_cast<unsigned>(size), stderr);
        (void)std::fflush(stderr); // Entry/progress survives abrupt process termination.
    }
    endCheckpoint(checkpoint);
    o.busy.clear(std::memory_order_release);
}
inline void bump(Field field) {
    if (!enabled()) return;
    State& s = state();
    // Scope helpers also serve typedef handling; only count active using scans.
    if (!s.v[Call]) return;
    increment(s.v[field]);
    if (++s.operations == SampleOperations) {
        s.operations = 0;
        emit(0, static_cast<unsigned>(s.v[Phase]));
    }
}
// Independent of the using-only Call field. No clock/log on individual visits.
inline void templateBump(Field field) noexcept {
    if (!enabled()) return;
    State& s = state();
    if (!s.v[ActiveBucket]) return;
    increment(s.v[field]);
    if (++s.operations == SampleOperations) {
        s.operations = 0;
        emit(0, 1);
    }
}
inline void distanceTokens(std::uint64_t count) {
    if (!enabled() || !state().v[Call]) return;
    auto& value = state().v[RhsDistanceTokens];
    const auto max = std::numeric_limits<std::uint64_t>::max();
    value = count > max - value ? max : value + count;
}
// Phase 1=template pass, 2=using call, 3=per-alias scan; event 0=sample,1=entry,2=exit.
class Frame {
    unsigned kind;
    std::uint64_t oldPhase = 0, oldPass = 0, oldCall = 0, oldAlias = 0;
public:
    explicit Frame(unsigned phase, unsigned pass = 0) : kind(phase) {
        if (!enabled()) return;
        State& s = state();
        oldPhase=s.v[Phase]; oldPass=s.v[Pass]; oldCall=s.v[Call]; oldAlias=s.v[Alias];
        s.v[Phase] = phase;
        if (phase == 1) s.v[Pass] = pass;
        if (phase == 2) { increment(s.v[UsingCalls]); s.v[Call]=s.v[UsingCalls]; s.v[Alias]=0; }
        if (phase == 3) { increment(s.v[Aliases]); s.v[Alias]=s.v[Aliases]; }
        emit(1, phase);
    }
    ~Frame() {
        if (!enabled()) return;
        emit(2, kind);
        State& s = state();
        s.v[Phase]=oldPhase; s.v[Pass]=oldPass; s.v[Call]=oldCall; s.v[Alias]=oldAlias;
    }
    Frame(const Frame&) = delete;
    Frame& operator=(const Frame&) = delete;
};
inline void instantiated() {
    if (!enabled()) return;
    increment(state().v[Instantiations]);
    emit(0, 1);
}
} // namespace NicoStage
#endif
