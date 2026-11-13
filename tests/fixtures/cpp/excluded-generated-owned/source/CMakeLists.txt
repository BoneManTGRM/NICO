cmake_minimum_required(VERSION 3.31)
project(owned_missing_generated LANGUAGES CXX)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
add_library(visible OBJECT main.cpp)
add_custom_command(OUTPUT "${CMAKE_BINARY_DIR}/generated/hidden.cpp"
 COMMAND "${CMAKE_COMMAND}" -E make_directory "${CMAKE_BINARY_DIR}/generated"
 COMMAND "${CMAKE_COMMAND}" -E copy "${CMAKE_CURRENT_SOURCE_DIR}/hidden.cpp.in" "${CMAKE_BINARY_DIR}/generated/hidden.cpp"
 DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/hidden.cpp.in" VERBATIM)
add_custom_target(hidden_inputs DEPENDS "${CMAKE_BINARY_DIR}/generated/hidden.cpp")
add_library(hidden OBJECT EXCLUDE_FROM_ALL "${CMAKE_BINARY_DIR}/generated/hidden.cpp")
set_property(TARGET hidden PROPERTY EXPORT_COMPILE_COMMANDS OFF)
