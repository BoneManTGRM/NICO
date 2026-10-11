struct Stop {
  __attribute__((noreturn)) int operator[](unsigned) const { __builtin_trap(); }
};
int attributed_control() { Stop s; s[0]; }
struct Continue { int operator[](unsigned) const { return 0; } };
int missing_return() { Continue s; s[0]; }
int genuine_finding() { int *p=nullptr; return *p; }
