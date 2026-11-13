// Owned lifecycle/work controls. SNAPSHOT and barriers are injected verbatim
// from the producer. This does not emulate Cppcheck parsing or qualification.
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
struct Token {
    std::string text = "Alias";
    bool shadowed = false;
    bool readable = true;
    const std::string& str() const {
        if (!readable) throw std::runtime_error("stale typeName read");
        return text;
    }
};
static std::vector<Token> tokens(8192);
static unsigned calls = 0;
static unsigned long visits = 0;
struct List { Token* front() { return tokens.data(); } };
std::set<const Token*> aliasShadowedTokens(Token*, const std::string&) {
    ++calls;
    std::set<const Token*> result;
    for (const auto& token : tokens) {
        ++visits;
        if (token.shadowed) result.insert(&token);
    }
    return result;
}
enum Event { Read, Query, QualificationEdit, OperatorEdit, InvalidateTypeName };
bool sweep(const std::vector<Event>& events, bool eligible = true) {
    // The independent eager oracle is the entry-state decision for the token.
    const bool expected = eligible && tokens[0].shadowed;
    const unsigned before = calls;
    Token declaration;
    Token* typeName = &declaration;
    List list;
    std::set<std::string> aliasNames;
    if (eligible) aliasNames.insert("Alias");
SNAPSHOT
    bool reached = false;
    for (Event event : events) {
        if (event == Query || event == QualificationEdit) {
            reached = true;
MATCH_BARRIER
            if (event == Query) {
                if (bool(aliasShadowed.count(&tokens[0])) != expected) {
                    std::cerr << "snapshot decision changed\n"; return false;
                }
            } else {
                // Qualification/RHS edits may change contents at the same address.
                tokens[0].shadowed = !tokens[0].shadowed;
                tokens[0].text = "Changed";
            }
        } else if (event == OperatorEdit || event == InvalidateTypeName) {
            reached = true;
MUTATION_BARRIER
            tokens[0].shadowed = !tokens[0].shadowed;
            if (event == InvalidateTypeName) declaration.readable = false;
        }
    }
    const unsigned expectedCalls = reached && eligible ? 1 : 0;
    if (calls - before != expectedCalls) {
        std::cerr << "snapshot construction count differs\n"; return false;
    }
    return true;
}
int main() {
    try {
        // Read-only/unused declarators must not scan the list at all.
        for (unsigned i = 0; i < 64; ++i)
            if (!sweep({Read, Read, Read})) return 1;
        if (calls || visits) return 1;
        // Exhaust short event sequences against the eager entry-state oracle.
        unsigned cases = 0;
        for (unsigned length = 0, count = 1; length <= 5; ++length, count *= 4) {
            for (unsigned code = 0; code < count; ++code) {
                std::vector<Event> events;
                unsigned value = code;
                for (unsigned i = 0; i < length; ++i, value /= 4)
                    events.push_back(static_cast<Event>(value % 4));
                for (bool initial : {false, true}) {
                    tokens[0].shadowed = initial;
                    if (!sweep(events)) return 1;
                    ++cases;
                }
            }
        }
        // Empty snapshots are ready; later guards must not re-read typeName.
        tokens[0].shadowed = false;
        if (!sweep({InvalidateTypeName, Query, OperatorEdit, Query})) return 1;
        // A following declarator must see fresh contents at the same address.
        tokens[0].shadowed = true;
        if (!sweep({QualificationEdit, Query}) || !sweep({Query})) return 1;
        if (!sweep({OperatorEdit, Query}, false)) return 1;
        const auto before = visits;
        if (!sweep({Query, Query, OperatorEdit, Query})) return 1;
        if (visits - before != tokens.size()) return 1;
        std::cout << "event_cases=" << cases
                  << " unused_sweeps=64 unused_visits=0 one_snapshot_visits=" << tokens.size() << "\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
