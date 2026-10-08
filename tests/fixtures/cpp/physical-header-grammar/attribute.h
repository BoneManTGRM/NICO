#pragma once
typedef unsigned long size_t;
template<typename _Tp, size_t _Nm> struct __array_traits {};
template<typename _Tp> struct __array_traits<_Tp, 0> {
  struct _Type {
    __attribute__((__always_inline__,__noreturn__))
    _Tp& operator[](size_t) const noexcept { __builtin_trap(); }
    __attribute__((__always_inline__))
    constexpr explicit operator _Tp*() const noexcept { return nullptr; }
  };
};
inline int header_bug() { int *p=nullptr; return *p; }
