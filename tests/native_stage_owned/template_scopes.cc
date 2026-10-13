#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <list>
#include <limits>
#include <stdexcept>
#include <chrono>
static std::uint64_t tick = 0, calls = 0;
static bool clockAvailable = true;
static bool fakeClock(std::uint64_t& ns) noexcept { ++calls; ns=tick; return clockAvailable; }
#ifndef REAL_CLOCK
#define NICO_STAGE_TEST_CLOCK fakeClock
#endif
#include "nico_stage_counters.h"
#define REQUIRE(x) do { if (!(x)) { std::fprintf(stdout,"failed line %d: %s\n",__LINE__,#x); std::exit(1); } } while (false)
using namespace NicoStage;
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
        return 0;
    }
    if (!enabled()) { Frame pass(1,1); TemplateScope s(1); templateBump(SelectionVisits); REQUIRE(calls==0); REQUIRE(state().v[SelectionEntered]==0); return 0; }
    state().v[Phase]=1;
    if (!std::strcmp(mode,"clock")) {
        { TemplateScope a(1); tick=10; checkpointCpu(); clockAvailable=false; tick=20; checkpointCpu(); clockAvailable=true; tick=30; checkpointCpu(); }
        REQUIRE(state().v[ThreadClockStatus]==2); REQUIRE(state().v[SelectionCpuNs]==10); emit(1,1); return 0;
    }
    if (!std::strcmp(mode,"unavailable")) {
        clockAvailable=false; { TemplateScope a(1); tick=10; checkpointCpu(); }
        REQUIRE(state().v[ThreadClockStatus]==2); REQUIRE(state().v[SelectionCpuNs]==0); emit(1,1); return 0;
    }
    if (!std::strcmp(mode,"rate")) {
        emit(1,1);
        for(unsigned i=0;i<100;++i) emit(0,1);
        REQUIRE(output().records==1);
        return 0;
    }
    if (!std::strcmp(mode,"visit-clock")) {
        TemplateScope select(1); const auto before=calls;
        for(unsigned i=0;i<4095;++i) templateBump(SelectionVisits);
        REQUIRE(calls==before);
        tick=12; templateBump(SelectionVisits);
        REQUIRE(calls==before+1); REQUIRE(state().v[SelectionCpuNs]==12);
        return 0;
    }
    if (!std::strcmp(mode,"backward")) {
        tick=10; TemplateScope select(1); tick=5; checkpointCpu();
        REQUIRE(state().v[ThreadClockStatus]==2); REQUIRE(state().v[SelectionCpuNs]==0);
        emit(1,1); return 0;
    }
    if (!std::strcmp(mode,"caps")) {
        for(unsigned f=OuterVisits;f<=ReplacementNestedVisits;++f) state().v[f]=std::numeric_limits<std::uint64_t>::max();
        increment(state().v[SelectionVisits]); addSaturated(state().v[SelectionCpuNs],1);
        REQUIRE(state().v[SelectionVisits]==std::numeric_limits<std::uint64_t>::max());
        REQUIRE(state().v[SelectionCpuNs]==std::numeric_limits<std::uint64_t>::max());
        for(unsigned i=0;i<200;++i) { output().last=std::chrono::steady_clock::time_point{}; emit(0,1); }
        REQUIRE(output().records==128); return 0;
    }
    if (!std::strcmp(mode,"snapshot")) {
        TemplateScope select(1); tick=10;
        TemplateScope expand(3); tick=40;
        // Represents the retained prefix at termination without requiring a signal.
        emit(1,1);
        REQUIRE(state().v[SelectionCpuNs]==10 && state().v[ExpansionCpuNs]==30);
        REQUIRE(state().v[SelectionCompleted]==0 && state().v[ExpansionCompleted]==0);
        return 0;
    }
    if (!std::strcmp(mode,"mutation")) {
        TemplateScope select(1); std::list<int> live{1,2,3}; unsigned encoded=0;
        for(auto it=live.begin();it!=live.end();) {
            templateBump(SelectionVisits); encoded=encoded*10+*it;
            if(*it==1) live.push_back(4);
            if(*it==2) it=live.erase(it); else ++it;
        }
        REQUIRE(encoded==1234); REQUIRE(state().v[SelectionVisits]==4);
        REQUIRE(live==std::list<int>({1,3,4})); return 0;
    }
    { TemplateScope select(1); tick=10;
      { TemplateScope same(1); tick=20;
        { TemplateScope different(3); tick=50; }
        tick=60;
      }
      tick=70; early();
      try { TemplateScope match(2); tick+=11; throw std::runtime_error("owned"); } catch(const std::runtime_error&) {}
      REQUIRE(state().v[ActiveBucket]==1 && state().v[BucketDepth]==1);
      tick+=3;
    }
    REQUIRE(state().v[ActiveBucket]==0 && state().v[BucketDepth]==0);
    REQUIRE(state().v[SelectionCpuNs]==43); REQUIRE(state().v[ExpansionCpuNs]==30);
    REQUIRE(state().v[ReplacementCpuNs]==7); REQUIRE(state().v[MatchingCpuNs]==11);
    REQUIRE(state().v[SelectionEntered]==2 && state().v[SelectionCompleted]==2);
    REQUIRE(state().v[MatchingEntered]==1 && state().v[MatchingCompleted]==0);
    REQUIRE(state().v[ReplacementEntered]==1 && state().v[ReplacementCompleted]==1);
    emit(1,1);
}
