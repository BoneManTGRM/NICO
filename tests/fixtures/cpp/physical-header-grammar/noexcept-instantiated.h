#pragma once
#define _GLIBCXX_NOEXCEPT_IF(...) noexcept(__VA_ARGS__)
template<typename _Iterator> struct reverse_iterator {
  _Iterator current;
  reverse_iterator(const reverse_iterator& __x)
  _GLIBCXX_NOEXCEPT_IF(noexcept(_Iterator(__x.current)))
  : current(__x.current) { }
};
reverse_iterator<int*> make(const reverse_iterator<int*>& x) { return reverse_iterator<int*>(x); }
inline int header_bug() { int *p=nullptr; return *p; }

template<typename T> T convert_argument(int* p) { return T(*p); }
inline int argument_finding() { return *convert_argument<int*>(nullptr); }
