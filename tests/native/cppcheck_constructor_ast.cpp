// Owned regression fixture for the pinned Cppcheck tool dependency.
// Compile with Cppcheck's test fixture and the patched libraries; see evidence README.
#include "fixture.h"
#include "helpers.h"
#include "settings.h"
#include "token.h"
#include "tokenize.h"
#include "tokenlist.h"
#include <sstream>
#include <string>

// Use the upstream friend test class name, in a separate runner that does not
// link upstream testtokenize.o. This keeps production headers unchanged.
class TestTokenizer : public TestFixture {
public:
    TestTokenizer() : TestFixture("TestNicoConstructorAst") {}
private:
    void run() override {
        TEST_CASE(parenthesized);
        TEST_CASE(braced);
        TEST_CASE(base);
        TEST_CASE(delegating);
        TEST_CASE(multiple);
        TEST_CASE(nestedConstraints);
        TEST_CASE(noexceptConstructor);
        TEST_CASE(trailingDecltype);
        TEST_CASE(variableTracking);
        TEST_CASE(functionDeclarator);
        TEST_CASE(pointerConversionArguments);
    }

    void initializer(const std::string& ending, unsigned expectedUses) {
        Settings settings;
        settings.standards.cpp = Standards::CPP20;
        Tokenizer tokenizer(settings, *this);
        std::istringstream input(
            "struct B { B(int = 0); }; template<class T> concept C = true; void f(); "
            "template<class T> struct A : B { int member; int other; A(int, int); A(int seed) "
            + ending + " {} };");
        ASSERT(tokenizer.list.createTokens(input, "owned.cpp"));
        tokenizer.combineOperators();
        tokenizer.createLinks();
        tokenizer.createLinks2();
        tokenizer.list.front()->assignIndexes();
        tokenizer.prepareTernaryOpForAST();
        tokenizer.list.createAst();
        tokenizer.list.validateAst(false);
        // A surviving token alone is insufficient: every initializer argument
        // must belong to the expression tree with reciprocal parent/child links.
        unsigned uses = 0;
        const Token* colon = Token::findsimplematch(tokenizer.list.front(), ": member");
        if (!colon)
            colon = Token::findsimplematch(tokenizer.list.front(), ": B (");
        if (!colon)
            colon = Token::findsimplematch(tokenizer.list.front(), ": A (");
        ASSERT(colon);
        for (const Token* tok = colon->next(); tok; tok = tok->next()) {
            if (tok->str() != "seed")
                continue;
            ++uses;
            ASSERT(tok->astParent());
            ASSERT(tok->astParent()->astOperand1() == tok || tok->astParent()->astOperand2() == tok);
        }
        ASSERT_EQUALS(expectedUses, uses);
    }

    void parenthesized() { initializer("requires true : member(seed + 1)", 1); }
    void braced() { initializer("requires true : member{seed + 1}", 1); }
    void base() { initializer("requires true : B(seed + 1)", 1); }
    void delegating() { initializer("requires true : A(seed + 1, 0)", 1); }
    void multiple() { initializer("requires true : member(seed + 1), other{seed + 2}", 2); }
    void nestedConstraints() {
        initializer("requires (C<T> && (sizeof(T) > 1 ? true : false)) : member(seed + 1)", 1);
        initializer("requires bool{C<T>} : member(seed + 1)", 1);
    }
    void noexceptConstructor() {
        initializer("noexcept(noexcept(f())) requires true : member(seed + 1)", 1);
    }
    void trailingDecltype() {
        Settings settings;
        settings.standards.cpp = Standards::CPP20;
        Tokenizer tokenizer(settings, *this);
        std::istringstream input("template<class T> auto f(T seed) noexcept(noexcept(g(seed))) "
                                 "-> decltype(g(seed)) requires true { return seed; }");
        ASSERT(tokenizer.list.createTokens(input, "owned.cpp"));
        tokenizer.combineOperators();
        tokenizer.createLinks();
        tokenizer.createLinks2();
        tokenizer.list.front()->assignIndexes();
        tokenizer.prepareTernaryOpForAST();
        tokenizer.list.createAst();
        tokenizer.list.validateAst(false);
        unsigned calls = 0;
        for (const Token* tok = tokenizer.list.front(); tok; tok = tok->next()) {
            if (!Token::simpleMatch(tok, "g ( seed )"))
                continue;
            ++calls;
            ASSERT(tok->astParent() == tok->next());
            ASSERT(tok->tokAt(2)->astParent() == tok->next());
        }
        ASSERT_EQUALS(2U, calls);
    }
    void variableTracking() {
        Settings settings;
        settings.standards.cpp = Standards::CPP20;
        SimpleTokenizer tokenizer(settings, *this);
        ASSERT(tokenizer.tokenize("template<class T> concept C = true; template<class T> struct A { int member; A(int seed) requires C<T> : member(seed + 1) {} };"));
        unsigned id = 0;
        unsigned uses = 0;
        for (const Token* tok = tokenizer.tokens(); tok; tok = tok->next()) {
            if (tok->str() != "seed")
                continue;
            ASSERT(tok->varId() != 0);
            if (id)
                ASSERT_EQUALS(id, tok->varId());
            id = tok->varId();
            ++uses;
        }
        ASSERT_EQUALS(2U, uses);
    }
    void functionDeclarator() {
        for (const char* code : {
                 "int* g(void* (f)(void*), void* u);",
                 "int* g(int* (f)(int*, int), int* u);"}) {
            Settings settings;
            Tokenizer tokenizer(settings, *this);
            std::istringstream input(code);
            ASSERT(tokenizer.list.createTokens(input, "owned.cpp"));
            tokenizer.combineOperators();
            tokenizer.createLinks();
            tokenizer.createLinks2();
            tokenizer.list.front()->assignIndexes();
            tokenizer.prepareTernaryOpForAST();
            tokenizer.list.createAst();
            tokenizer.list.validateAst(false);
            const Token* name = Token::findsimplematch(tokenizer.list.front(), "f ) (");
            ASSERT(name);
            ASSERT(!name->astParent());
            ASSERT(!name->astOperand1());
            ASSERT(!name->astOperand2());
        }
    }
    void pointerConversionArguments() {
        // These are post-template-substitution parser forms, not C++ syntax
        // acceptance tests. Their argument expressions must retain an AST.
        for (const char* code : {
                 "use(int * (seed));",
                 "use(int * (seed + 1));",
                 "use(int * (*seed));"}) {
            Settings settings;
            Tokenizer tokenizer(settings, *this);
            std::istringstream input(code);
            ASSERT(tokenizer.list.createTokens(input, "owned.cpp"));
            tokenizer.combineOperators();
            tokenizer.createLinks();
            tokenizer.createLinks2();
            tokenizer.list.front()->assignIndexes();
            tokenizer.prepareTernaryOpForAST();
            tokenizer.list.createAst();
            tokenizer.list.validateAst(false);
            const Token* seed = Token::findsimplematch(tokenizer.list.front(), "seed");
            ASSERT(seed);
            ASSERT(seed->astParent());
            ASSERT(seed->astParent()->astOperand1() == seed || seed->astParent()->astOperand2() == seed);
        }
    }
};

REGISTER_TEST(TestTokenizer)
