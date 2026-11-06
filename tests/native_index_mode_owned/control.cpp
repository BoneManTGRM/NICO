#include "tokenlist.h"
#include "nico_stage_counters.h"
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <cstring>
static long failAfter=-1;
void* operator new(std::size_t n){if(failAfter==0){failAfter=-1;throw std::bad_alloc();}if(failAfter>0)--failAfter;if(void*p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void operator delete(void*p)noexcept{std::free(p);}
using namespace NicoStage;
static void clear(){state()=State();}
static void reason(unsigned expected){assert(state().v[FirstDisableReason]==(enabled()?expected:0));}
static void active(){clear();TokensFrontBack l;Token a("A"),x("<"),b("B"),y("<");for(auto*t:{&a,&x,&b,&y})l.add(t);auto*p=l.lessTokens();assert(p&&p->size()==2);indexQuery(true);for(auto*t:*p){assert(t);indexSelected(true);}if(enabled()){assert(state().v[SuccessfulBuilds]==1&&state().v[IndexBuildVisits]==4);assert(state().v[IndexedQueries]==1&&state().v[IndexedSelected]==2);assert(state().v[PeakLiveSlots]==2&&state().v[PeakTotalSlots]==2);}reason(0);l.removedLessToken(&x);assert(l.mLessValid);l.removedLessToken(&y);assert(!l.mLessValid);indexSelected(false);indexQuery(false);reason(3);if(enabled())assert(state().v[LinearSelected]==1&&state().v[FallbackQueries]==1);}
static void reasons(){
 {clear();TokensFrontBack l;Token a("<");l.add(&a);failAfter=0;assert(!l.lessTokens());failAfter=-1;reason(1);assert(l.mLessDisabled);}
 {clear();TokensFrontBack l;Token a("<"),b("<");l.add(&a);assert(l.lessTokens());l.add(&b);failAfter=0;l.insertedLessToken(&b);failAfter=-1;assert(l.back==&b&&!l.mLessValid);reason(2);}
 {clear();TokensFrontBack l;Token a("A"),b("<");l.add(&a);l.add(&b);assert(l.lessTokens());a.text="<";l.changedLessToken(&a);assert(!l.mLessValid);reason(4);}
 {clear();TokensFrontBack l;Token a("<"),b("B"),x("<");l.add(&a);l.add(&b);assert(l.lessTokens());x.before=&a;x.after=&b;a.after=&x;b.before=&x;l.insertedLessToken(&x);assert(!l.mLessValid);reason(5);assert(l.lessTokens());indexQuery(true);reason(5);if(enabled()){assert(state().v[SuccessfulBuilds]==2);assert(state().v[IndexedQueries]==1);}l.insertedLessToken(&x);assert(!l.lessTokens());reason(5);}
 {clear();TokensFrontBack l;Token a("<");l.add(&a);l.invalidateLessTokens();reason(0);assert(l.lessTokens());l.invalidateLessTokens();assert(!l.lessTokens());reason(6);indexDisable(IndexBuildAlloc);reason(6);}
}
static void dense(){clear();TokensFrontBack l;std::vector<Token*>tokens;for(int i=0;i<512;++i){auto*t=new Token("<");tokens.push_back(t);l.add(t);}assert(l.lessTokens()->size()==512);Token tail("<");l.add(&tail);l.insertedLessToken(&tail);assert(l.mLessTokens.size()==513);if(enabled()){assert(state().v[PeakLiveSlots]==513&&state().v[PeakTotalSlots]==513);assert(state().v[IndexBuildVisits]==512);}for(auto*t:tokens)delete t;}
int main(int argc,char**argv){
 if(argc>1&&std::strcmp(argv[1],"overflow-cap")==0){for(unsigned i=0;i<Count;++i)state().v[i]=std::numeric_limits<std::uint64_t>::max();for(unsigned i=0;i<140;++i){output().last=std::chrono::steady_clock::time_point();emit(1,1);}assert(output().records==128);return 0;}
 if(argc>1&&std::strcmp(argv[1],"overflow")==0){for(unsigned i=0;i<Count;++i)state().v[i]=std::numeric_limits<std::uint64_t>::max();emit(1,1);return 0;}
 active();reasons();dense();clear();const auto max=std::numeric_limits<std::uint64_t>::max();state().v[IndexedQueries]=max;indexQuery(true);assert(state().v[IndexedQueries]==max);state().v[IndexedSelected]=max;indexSelected(true);assert(state().v[IndexedSelected]==max);state().v[SuccessfulBuilds]=max;indexBuilt(1,1);assert(state().v[SuccessfulBuilds]==max);state().v[IndexBuildVisits]=max;indexBuildVisit();assert(state().v[IndexBuildVisits]==max);
 clear();std::thread a([]{active();});std::thread b([]{active();});a.join();b.join();assert(state().v[IndexedQueries]==0);if(!enabled())for(auto x:state().v)assert(x==0);
 std::cout<<"owned_index_mode_controls=pass observer="<<enabled()<<"\n";
}
