#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <list>
#include <limits>
#include <stdexcept>
#include <chrono>
static std::uint64_t tick = 0, calls = 0, step = 0;
static bool clockAvailable = true;
static bool fakeClock(std::uint64_t& ns) noexcept { ++calls; ns=tick; tick+=step; return clockAvailable; }
#ifndef REAL_CLOCK
#define NICO_STAGE_TEST_CLOCK fakeClock
#endif
#include "nico_stage_counters.h"
#define REQUIRE(x) do { if (!(x)) { std::fprintf(stdout,"failed line %d: %s\n",__LINE__,#x); std::exit(1); } } while (false)
using namespace NicoStage;
static void sample(std::uint64_t pre, std::uint64_t post) {
    tick=pre; step=post-pre;
    output().last=std::chrono::steady_clock::time_point{}; emit(0,1);
    step=0;
}
static void early() { TemplateScope scope(4); tick += 7; return; }
int main(int argc, char** argv) {
    const char* mode=argc>1?argv[1]:"scopes";
    if (!std::strcmp(mode,"overhead")) {
        volatile std::uint64_t sum=0;
        const auto start=std::chrono::steady_clock::now();
        { Frame pass(1,1); TemplateScope select(1);
          for (unsigned i=0;i<2000000;++i) { sum+=i; templateBump(SelectionVisits); }
          for (unsigned i=0;i<100000;++i) { TemplateScope match(2); sum+=i; }
        }
        std::printf("%lld %llu\n",static_cast<long long>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count()),static_cast<unsigned long long>(sum));
        std::printf("clock_reads=%llu transitions=%llu\n",static_cast<unsigned long long>(state().v[ClockReads]),static_cast<unsigned long long>(state().v[TransitionId]));
        return 0;
    }
    if (!enabled()) { Frame pass(1,1); TemplateScope s(1); templateBump(SelectionVisits); REQUIRE(calls==0); REQUIRE(state().v[SelectionEntered]==0); return 0; }
    state().v[Phase]=1;
    if (!std::strcmp(mode,"clock") || !std::strcmp(mode,"unavailable")) {
        TemplateScope a(1);
        if (!std::strcmp(mode,"clock")) sample(10,12);
        clockAvailable=false; sample(20,22); const auto n=calls;
        clockAvailable=true; sample(30,32);
        REQUIRE(state().v[ThreadClockStatus]==2 && state().v[IntervalKind]==7);
        REQUIRE(calls==n && state().v[StableSelectionNs]==0); return 0;
    }
    if (!std::strcmp(mode,"rate")) {
        sample(0,2); const auto n=calls;
        for(unsigned i=0;i<100;++i) emit(0,1);
        REQUIRE(output().records==1 && calls==n); return 0;
    }
    if (!std::strcmp(mode,"visit-clock")) {
        TemplateScope select(1); REQUIRE(calls==0);
        for(unsigned i=0;i<4095;++i) templateBump(SelectionVisits);
        REQUIRE(calls==0); tick=12; templateBump(SelectionVisits);
        REQUIRE(calls==2 && output().records==1);
        for(unsigned i=0;i<4096;++i) templateBump(SelectionVisits);
        REQUIRE(calls==2); return 0;
    }
    if (!std::strcmp(mode,"backward")) {
        TemplateScope select(1); sample(10,12); sample(5,7);
        REQUIRE(state().v[ThreadClockStatus]==2 && state().v[StableSelectionNs]==0); return 0;
    }
    if (!std::strcmp(mode,"post-failure")) {
        TemplateScope select(1); sample(10,8); sample(20,22);
        REQUIRE(state().v[ThreadClockStatus]==2 && state().v[IntervalKind]==7); return 0;
    }
    if (!std::strcmp(mode,"saturation")) {
        TemplateScope select(1); state().v[TransitionId]=std::numeric_limits<std::uint64_t>::max()-1;
        { TemplateScope same(1); }
        REQUIRE(state().v[TransitionSaturated]==1); sample(10,12); sample(22,24);
        REQUIRE(state().v[IntervalKind]==5 && state().v[UnattributedNs]==10);
        auto& value=state().v[SelectionVisits]; value=std::numeric_limits<std::uint64_t>::max();
        increment(value); REQUIRE(value==std::numeric_limits<std::uint64_t>::max());
        return 0;
    }
    if (!std::strcmp(mode,"caps")) {
        for(unsigned i=0;i<200;++i) sample(2*i,2*i+1);
        REQUIRE(output().records==128 && calls==256); return 0;
    }
    if (!std::strcmp(mode,"snapshot")) {
        TemplateScope select(1); TemplateScope expand(3); sample(10,12); sample(42,47);
        REQUIRE(state().v[StableExpansionNs]==30 && state().v[ObserverNs]==7);
        REQUIRE(state().v[SelectionCompleted]==0 && state().v[ExpansionCompleted]==0); return 0;
    }
    if (!std::strcmp(mode,"mutation")) {
        TemplateScope select(1); std::list<int> live{1,2,3}; unsigned encoded=0;
        for(auto it=live.begin();it!=live.end();) {
            templateBump(SelectionVisits); encoded=encoded*10+*it;
            if(*it==1) live.push_back(4);
            if(*it==2) it=live.erase(it); else ++it;
        }
        REQUIRE(encoded==1234 && calls==0); REQUIRE(state().v[SelectionVisits]==4);
        REQUIRE(live==std::list<int>({1,3,4})); return 0;
    }
    if (!std::strcmp(mode,"cross-checkpoint")) {
        TemplateScope select(1);
        // Owned simulation of a reentrant transition during observer processing.
        tick=10; step=0; const auto c=beginCheckpoint();
        { TemplateScope child(2); }
        tick=15; endCheckpoint(c); REQUIRE(!state().baselineValid);
        tick=30; const auto next=beginCheckpoint();
        REQUIRE(state().v[IntervalKind]==0 && state().v[StableSelectionNs]==0);
        tick=32; endCheckpoint(next); return 0;
    }
    { TemplateScope select(1); sample(0,2); const auto n=calls;
      { TemplateScope child(3); }
      REQUIRE(calls==n); sample(42,44); REQUIRE(state().v[IntervalKind]==5);
      { TemplateScope same(1); }
      sample(84,86); REQUIRE(state().v[IntervalKind]==5);
      sample(126,128); REQUIRE(state().v[IntervalKind]==1 && state().v[StableSelectionNs]==40);
      early();
      try { TemplateScope match(2); throw std::runtime_error("owned"); } catch(const std::runtime_error&) {}
      REQUIRE(state().v[ActiveBucket]==1 && state().v[BucketDepth]==1);
    }
    REQUIRE(state().v[ActiveBucket]==0 && state().v[BucketDepth]==0);
    REQUIRE(state().v[SelectionEntered]==2 && state().v[SelectionCompleted]==2);
    REQUIRE(state().v[MatchingEntered]==1 && state().v[MatchingCompleted]==0);
    REQUIRE(state().v[ReplacementEntered]==1 && state().v[ReplacementCompleted]==1);
    sample(170,172); REQUIRE(state().v[IntervalKind]==5);
    sample(202,204); REQUIRE(state().v[IntervalKind]==6 && state().v[OutsideNs]==30);
}
