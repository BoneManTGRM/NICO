#pragma once
namespace capnp { enum class Kind { PRIMITIVE, ENUM }; template<typename T> constexpr Kind kind() { return Kind::PRIMITIVE; } }
#define CAPNP_KIND(T) ::capnp::kind<T>()
using capnp::Kind;
template <typename T, Kind kind = CAPNP_KIND(T)> struct Mask_;
template <typename T> struct Mask_<T, Kind::PRIMITIVE> { typedef T Type; };
inline int header_bug() { int *p=nullptr; return *p; }
