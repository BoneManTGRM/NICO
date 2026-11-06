#include <vector>
#include <unordered_map>
#include <string>
#include <new>
struct Token {
 std::string text; Token* before=nullptr;Token* after=nullptr;
 explicit Token(const char* s):text(s){}
 const std::string& str()const{return text;}
 Token* next()const{return after;} Token* previous()const{return before;}
};
struct TokensFrontBack {
 Token* front=nullptr;Token* back=nullptr;
 bool mLessValid=false,mLessDisabled=false;
 std::vector<Token*> mLessTokens;std::unordered_map<Token*,std::size_t>mLessSlots;
 const std::vector<Token*>* lessTokens(); void invalidateLessTokens();
 void removedLessToken(Token*);void changedLessToken(Token*);void insertedLessToken(Token*);
 void add(Token*t){t->before=back;if(back)back->after=t;else front=t;back=t;}
};
