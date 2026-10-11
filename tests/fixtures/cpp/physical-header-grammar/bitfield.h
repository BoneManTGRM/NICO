#pragma once
struct Bits { unsigned flag : 1 {}; unsigned reserved : 15 {}; };
inline int header_bug(){int *p=nullptr;return *p;}
