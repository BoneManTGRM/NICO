#pragma once
namespace ns { constexpr int kind = 1; }
template<int kind, bool b = ns::kind < 2> struct S { int value; };
S<0> s;
inline int header_bug() { int *p = nullptr; return *p; }
