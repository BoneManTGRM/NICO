#include "sum.hpp"
#include <iostream>
#include <string>
int main(int argc, char** argv) {
 if (argc != 2) return 9;
 const std::string mode(argv[1]);
 if (mode == "negative") { std::cerr << "NICO deliberate negative control: exit 7\n"; return 7; }
 if (mode == "unit") return control_sum(19,23)==42 ? 0 : 1;
 if (mode == "integration") { int value=0; for(int i=0;i<10;++i) value=control_sum(value,i); std::cout << value << "\n"; return value==45 ? 0 : 2; }
 return 8;
}
