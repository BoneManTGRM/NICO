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

namespace NicoStage {
enum Field : unsigned {
    Phase, Pass, Call, Alias, OuterVisits, InnerVisits, ScopeNodes, MatchCalls,
    BaseQueries, BaseVisits, ScopeQueries, ChildVisits, Replacements, Instantiations,
    UsingCalls, Aliases, RhsDistanceCalls, RhsDistanceTokens, RhsParses, PreludeVisits, Count
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
    char line[MaxRecordBytes];
    const auto wall = std::chrono::duration_cast<std::chrono::microseconds>(now - o.start).count();
    const std::clock_t cpu = std::clock();
    int size = std::snprintf(line, sizeof(line), "NICO_STAGE_V1 %u %u %u %u %llu %lld %llu",
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
