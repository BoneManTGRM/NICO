#ifdef NDEBUG
#error "Owned native controls require active assertions"
#endif
#include "token.h"
#include "tokenlist.h"
#include "settings.h"
#include <cstdlib>
#include <new>
#include <cassert>
#include <iostream>
#include <set>
#include <cstdint>
static long failBudget=-1;
static bool countAlloc=false;
static unsigned allocs=0, faults=0, activeChecks=0, disabledChecks=0;
void* operator new(std::size_t n) {
    if(countAlloc) ++allocs;
    if(failBudget==0){ failBudget=-1; ++faults; throw std::bad_alloc(); }
    if(failBudget>0)--failBudget;
    if(void*p=std::malloc(n))return p;
    throw std::bad_alloc();
}
void operator delete(void*p) noexcept {std::free(p);}
static void populate(TokenList& l) {for(const char*s:{"A","<","B","<","C","<","D","<"})l.addtoken(s,1,1,0);}
static void verify(TokenList& l) {
    const auto*p=l.lessTokens();
    if(!p){++disabledChecks;assert(!l.lessTokensValid());return;}
    ++activeChecks;
    std::vector<Token*> a,b;
    for(auto*t:*p)if(t)a.push_back(t);
    for(auto*t=l.front();t;t=t->next())if(t->str()=="<")b.push_back(t);
    assert(a==b);
    assert(p->size()<=2*b.size());
}
static unsigned fillCapacity(TokenList& l) {
    populate(l);
    const auto* index=l.lessTokens();
    assert(index);
    unsigned appended=0;
    while(index->size()<index->capacity()) {
        assert(++appended<65536);
        l.addtoken("<",1,1,0);
        assert(l.lessTokensValid());
    }
    return index->size();
}
int main(){Settings settings;
    unsigned initialFaults=0,appendFaults=0,initialAllocs=0;
    {TokenList l(&settings);populate(l);allocs=0;countAlloc=true;assert(l.lessTokens());countAlloc=false;initialAllocs=allocs;}
    assert(initialAllocs>0);
    for(unsigned budget=0;budget<=initialAllocs;++budget){TokenList l(&settings);populate(l);unsigned old=faults;failBudget=budget;const auto*p=l.lessTokens();failBudget=-1;if(faults!=old){++initialFaults;assert(!p);failBudget=0;assert(!l.lessTokens());assert(failBudget==0);failBudget=-1;}else verify(l);}
    unsigned originalAllocs,extraAllocs;
    {TokenList l(&settings);populate(l);allocs=0;countAlloc=true;l.addtoken("<",1,1,0);countAlloc=false;originalAllocs=allocs;}
    {TokenList l(&settings);fillCapacity(l);allocs=0;countAlloc=true;l.addtoken("<",1,1,0);countAlloc=false;assert(allocs>originalAllocs);extraAllocs=allocs-originalAllocs;}
    // Full vector capacity guarantees a vector allocation after map insertion.
    // Enumerate every extra allocation, allowing implementation-specific map rehash.
    assert(extraAllocs>=2);
    for(unsigned offset=0;offset<=extraAllocs;++offset){TokenList l(&settings);unsigned before=fillCapacity(l);unsigned old=faults;failBudget=originalAllocs+offset;l.addtoken("<",1,1,0);failBudget=-1;assert(l.back()->str()=="<");unsigned less=0;for(auto*t=l.front();t;t=t->next())if(t->str()=="<")++less;assert(less==before+1);if(faults!=old){++appendFaults;assert(!l.lessTokens());failBudget=0;assert(!l.lessTokens());assert(failBudget==0);failBudget=-1;}else verify(l);}
    assert(initialFaults==initialAllocs&&appendFaults==extraAllocs);
    {TokenList l(&settings);populate(l);assert(l.lessTokens());Token::replace(l.front()->tokAt(2),l.front()->tokAt(4),l.front()->tokAt(5));assert(!l.lessTokens());}
    {TokenList l(&settings);populate(l);assert(l.lessTokens());Token*tail=l.back();tail->str("");assert(l.lessTokensValid());assert(tail->insertToken("<")==tail);assert(l.back()==tail);assert(!l.lessTokens());}
    {TokenList l(&settings);l.addtoken("<",1,1,0);assert(l.lessTokens());l.front()->deleteThis();assert(l.front()==l.back()&&l.front()->str()==";");assert(!l.lessTokens());}
    {TokenList l(&settings);for(int i=0;i<1000;++i){l.addtoken("A",1,1,0);l.addtoken("<",1,1,0);}assert(l.lessTokens()->size()==1000);for(int i=0;i<501;++i){Token*t=l.front();while(t->next()&&t->next()->str()!="<")t=t->next();t->deleteNext();if(i<500)assert(l.lessTokensValid());}assert(!l.lessTokens());for(int i=0;i<100;++i)assert(!l.lessTokens());}
    unsigned edits=0,reuses=0,randomActive=0,randomDisabled=0;std::uint32_t rng=1983;std::set<std::uintptr_t> dead;
    for(unsigned seed=0;seed<40;++seed){TokenList l(&settings);populate(l);verify(l);
        for(unsigned n=0;n<100;++n){rng=rng*1664525u+1013904223u;unsigned op=rng%4;
            if(op<2){l.addtoken(op?"<":"identifier",1,1,0);if(dead.count(reinterpret_cast<std::uintptr_t>(l.back())))++reuses;}
            else {std::vector<Token*> all;for(auto*t=l.front();t;t=t->next())all.push_back(t);auto*t=all[(rng>>8)%all.size()];if(op==2&&t->next()){dead.insert(reinterpret_cast<std::uintptr_t>(t->next()));t->deleteNext();}else t->str(t->str()=="<"?">":"other");}
            if(l.lessTokensValid())++randomActive;else++randomDisabled;
            verify(l);++edits;
        }
    }
    std::cout<<"initial_allocation_faults="<<initialFaults<<" original_append_allocations="<<originalAllocs<<" append_cache_faults="<<appendFaults<<" random_edits="<<edits<<" observed_address_reuses="<<reuses<<" random_active="<<randomActive<<" random_disabled="<<randomDisabled<<" active_checks="<<activeChecks<<" disabled_checks="<<disabledChecks<<"\n";
}
