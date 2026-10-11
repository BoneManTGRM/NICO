// Owned scope/lookup fixtures. The ScopeInfo3 and candidate kernels are injected
// verbatim from the production repair; this does not emulate full tokenization.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <list>
#include <map>
#include <set>
#include <string>
#include <vector>
using std::size_t;
struct Token {};
static size_t scopeSearches = 0;
static size_t queryExpansions = 0;
SCOPES
MEMO
struct Lookup { Token* token; const ScopeInfo3* scope; size_t order; };
struct AliasEnd { Lookup alias; size_t endOrder; };
std::set<const Token*> candidate(const std::vector<Lookup>& uses, const std::vector<AliasEnd>& aliasEnds) {
BODY
}
// Independent straightforward previous lookup contract, including order rules.
std::set<const Token*> reference(const std::vector<Lookup>& uses, const std::vector<AliasEnd>& aliases) {
    std::set<const Token*> result;
    for (const auto& use : uses) for (const auto& entry : aliases) {
        const auto& alias = entry.alias;
        const bool declaration = use.token == alias.token;
        if (!declaration && use.order > alias.order && use.order <= entry.endOrder) continue;
        for (auto scope = use.scope; scope; scope = scope->parent) {
            if (alias.scope->type == ScopeInfo3::Record) {
                const bool same = (scope->type == ScopeInfo3::MemberFunction && scope->fullName == alias.scope->fullName) ||
                                  scope->findTypeInBase(alias.scope->fullName);
                if (scope == alias.scope || same) { result.insert(use.token); break; }
            } else if ((scope == alias.scope || (scope->type == ScopeInfo3::Namespace &&
                        alias.scope->type == ScopeInfo3::Namespace && scope->fullName == alias.scope->fullName)) &&
                       (declaration || use.order > entry.endOrder)) {
                result.insert(use.token); break;
            }
        }
    }
    return result;
}
ScopeInfo3* record(ScopeInfo3& root, const std::string& name) {
    return root.addChild(ScopeInfo3::Record, name, nullptr, nullptr);
}
bool equal(const std::vector<Lookup>& uses, const std::vector<AliasEnd>& aliases) {
    if (candidate(uses, aliases) != reference(uses, aliases)) {
        std::cerr << "visibility differs\n"; return false;
    }
    return true;
}
int main() {
    Token tokens[16];
    // Exhaust all forward-only inheritance graphs on five records and all
    // declaring/use scopes, then repeat with a changed graph using the same nodes.
    for (unsigned graph = 0; graph < 1024; ++graph) {
        ScopeInfo3 root; std::vector<ScopeInfo3*> nodes;
        for (int i = 0; i < 5; ++i) nodes.push_back(record(root, "R" + std::to_string(i)));
        unsigned bit = 0;
        for (int i = 0; i < 5; ++i) for (int j = 0; j < i; ++j, ++bit)
            if (graph & (1u << bit)) nodes[i]->baseTypes.insert(nodes[j]->name);
        std::vector<Lookup> uses;
        std::vector<AliasEnd> aliases;
        for (int i = 0; i < 5; ++i) {
            uses.push_back({&tokens[i], nodes[i], 20u + unsigned(i)});
            aliases.push_back({{&tokens[5+i], nodes[i], unsigned(i)}, 10});
        }
        if (!equal(uses, aliases)) return 1;
        nodes[4]->baseTypes.clear();
        if (!equal(uses, aliases)) return 1;
    }
    ScopeInfo3 root;
    auto base = record(root, "Base"); auto leaf = record(root, "Leaf"); auto other = record(root, "Other");
    leaf->baseTypes.insert("Base");
    auto function = root.addChild(ScopeInfo3::MemberFunction, "Base", nullptr, nullptr);
    auto nested = leaf->addChild(ScopeInfo3::Other, "", nullptr, nullptr);
    auto ns1 = root.addChild(ScopeInfo3::Namespace, "N", nullptr, nullptr);
    auto ns2 = root.addChild(ScopeInfo3::Namespace, "N", nullptr, nullptr);
    std::vector<AliasEnd> aliases = {{{&tokens[0],base,4},8}, {{&tokens[1],other,12},15}, {{&tokens[2],ns1,2},3}};
    std::vector<Lookup> uses = {{&tokens[0],base,4}, {&tokens[3],base,6}, {&tokens[4],nested,20},
        {&tokens[5],function,21}, {&tokens[6],other,22}, {&tokens[7],ns2,23}, {&tokens[8],&root,24},
        {&tokens[9],nested,25}, {&tokens[10],function,26}};
    if (!equal(uses, aliases)) return 1;
    const auto found = candidate(uses, aliases);
    if (found.count(&tokens[3]) || found.count(&tokens[8]) || !found.count(&tokens[7]) || !found.count(&tokens[4])) return 1;
    // Another declaration in the same record still makes an RHS visible,
    // exactly as the previous per-entry set-union contract does.
    aliases.push_back({{&tokens[11],base,1},2});
    if (!equal(uses, aliases) || !candidate(uses, aliases).count(&tokens[3])) return 1;
    leaf->baseTypes.clear();
    if (!equal(uses, aliases) || candidate(uses, aliases).count(&tokens[4])) return 1;
    // Unresolved direct base spelling is still a match; do not require findScope.
    ScopeInfo3 unresolved; unresolved.baseTypes.insert("Missing");
    AliasBaseResolutions resolutions; std::map<const ScopeInfo3*,bool> memo;
    if (!aliasTypeInBase(&unresolved,"Missing",memo,resolutions)) return 1;
    memo.clear();
    if (aliasTypeInBase(&unresolved,"",memo,resolutions)) return 1;
    // Preserve immediate self-base failure, even when a later base would match.
    auto repeated = record(root,"Repeat");
    auto recursive = repeated->addChild(ScopeInfo3::Record,"Repeat",nullptr,nullptr);
    recursive->baseTypes.insert("Repeat :: Repeat"); recursive->baseTypes.insert("Z");
    auto z = record(root,"Z"); z->baseTypes.insert("Good");
    memo.clear();
    if (recursive->findScope("Repeat :: Repeat") != recursive || recursive->findTypeInBase("Good") ||
        aliasTypeInBase(recursive,"Good",memo,resolutions)) return 1;
    // Layered shared negative subgraphs: the previous method expands paths;
    // the candidate resolves each distinct base edge once.
    ScopeInfo3 diamond; std::vector<ScopeInfo3*> layer;
    for (int depth = 0; depth < 19; ++depth) {
        std::vector<ScopeInfo3*> next;
        for (int side = 0; side < 2; ++side) {
            auto node = record(diamond,"D"+std::to_string(depth)+"_"+std::to_string(side));
            for (auto previous : layer) node->baseTypes.insert(previous->name);
            next.push_back(node);
        }
        layer = next;
    }
    scopeSearches=0;
    const auto before=std::chrono::steady_clock::now();
    if (layer.front()->findTypeInBase("Absent")) return 1;
    const auto baselineSearches=scopeSearches;
    const auto middle=std::chrono::steady_clock::now();
    scopeSearches=0; queryExpansions=0; memo.clear(); resolutions.clear();
    if (aliasTypeInBase(layer.front(),"Absent",memo,resolutions)) return 1;
    const auto candidateSearches=scopeSearches;
    const auto after=std::chrono::steady_clock::now();
    // Repeated/alternating uses reuse the completed scope query for one target.
    if (aliasTypeInBase(layer.back(),"Absent",memo,resolutions)) return 1;
    if (memo.size()!=38 || queryExpansions!=38 || scopeSearches!=candidateSearches+2 || candidateSearches!=70) {
        std::cerr << "shared graph work unbounded: " << candidateSearches << "\n"; return 1;
    }
    std::cout << "graph_cases=1024 mutation_rebuilt=1 diamond_baseline_searches=" << baselineSearches
              << " diamond_candidate_searches=" << candidateSearches << " baseline_us="
              << std::chrono::duration_cast<std::chrono::microseconds>(middle-before).count()
              << " candidate_us=" << std::chrono::duration_cast<std::chrono::microseconds>(after-middle).count() << "\n";
}
