cmake_minimum_required(VERSION 3.22)
project(lens_ime LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(LEVELDB_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LEVELDB_BUILD_BENCHMARKS OFF CACHE BOOL "" FORCE)
set(LEVELDB_INSTALL OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_INSTALL OFF CACHE BOOL "" FORCE)
set(ENABLE_TOOLS OFF CACHE BOOL "" FORCE)
get_filename_component(VENDOR "${CMAKE_CURRENT_LIST_DIR}/../../runtime/native-sources" ABSOLUTE)
add_subdirectory("${VENDOR}/leveldb" leveldb)
add_subdirectory("${VENDOR}/yaml-cpp" yaml-cpp)
add_subdirectory("${VENDOR}/marisa-trie" marisa)

# Compile OpenCC's library only. No executable tools, dictionaries or plugins.
set(OPENCC "${VENDOR}/OpenCC")
set(OPENCC_SOURCES Config Conversion ConversionChain Converter Dict DictConverter
    DictEntry DictGroup Lexicon MarisaDict MaxMatchSegmentation PhraseExtract
    SerializedValues SimpleConverter Segmentation TextDict UTF8StringSlice UTF8Util)
list(TRANSFORM OPENCC_SOURCES PREPEND "${OPENCC}/src/")
list(TRANSFORM OPENCC_SOURCES APPEND ".cpp")
add_library(lens_opencc STATIC ${OPENCC_SOURCES})
configure_file("${OPENCC}/src/opencc_config.h.in" "${CMAKE_CURRENT_BINARY_DIR}/opencc_config.h")
include(GenerateExportHeader)
generate_export_header(lens_opencc BASE_NAME OPENCC EXPORT_MACRO_NAME OPENCC_EXPORT
    EXPORT_FILE_NAME Opencc_Export.h STATIC_DEFINE Opencc_BUILT_AS_STATIC)
target_include_directories(lens_opencc PUBLIC "${OPENCC}/src" "${CMAKE_CURRENT_BINARY_DIR}"
    PRIVATE "${OPENCC}/deps/rapidjson-1.1.0")
target_compile_definitions(lens_opencc PUBLIC Opencc_BUILT_AS_STATIC PRIVATE PKGDATADIR=".")
target_link_libraries(lens_opencc PUBLIC marisa)
# librime uses opencc/ prefixed includes. Copy headers without changing upstream sources.
file(GLOB OPENCC_HEADERS "${OPENCC}/src/*.hpp" "${OPENCC}/src/*.h")
file(COPY ${OPENCC_HEADERS} DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/include/opencc")

set(RIME "${VENDOR}/librime")
configure_file("${RIME}/src/rime/build_config.h.in" "${CMAKE_CURRENT_BINARY_DIR}/include/rime/build_config.h")
file(GLOB RIME_SOURCES CONFIGURE_DEPENDS "${RIME}/src/*.cc" "${RIME}/src/rime/*.cc"
    "${RIME}/src/rime/algo/*.cc" "${RIME}/src/rime/config/*.cc"
    "${RIME}/src/rime/dict/*.cc" "${RIME}/src/rime/gear/*.cc" "${RIME}/src/rime/lever/*.cc")
add_library(lens_rime SHARED ${RIME_SOURCES} cpp/rime_bridge.cpp)
target_include_directories(lens_rime PRIVATE "${RIME}/src" "${RIME}/include"
    "${VENDOR}/boost" "${CMAKE_CURRENT_BINARY_DIR}/include")
target_compile_definitions(lens_rime PRIVATE RIME_VERSION="1.17.0" RIME_EXTRA_MODULES=
    RIME_NO_THREADING RIME_NO_TIMESTAMP BOOST_DLL_USE_STD_FS YAML_CPP_STATIC_DEFINE)
target_link_libraries(lens_rime PRIVATE yaml-cpp leveldb marisa lens_opencc log)
# OpenCC 1.1.9 headers use C++17-deprecated std::iterator. Keep the warning;
# don't inherit LevelDB's global -Werror for this upstream deprecation.
target_compile_options(lens_rime PRIVATE -Wno-error=deprecated-declarations)
target_link_options(lens_rime PRIVATE "-Wl,-z,max-page-size=16384")

# Runs the real linked engine on a connected Android/emulator with synthetic input.
add_executable(rime_smoke cpp/rime_smoke.cpp)
target_include_directories(rime_smoke PRIVATE "${RIME}/src")
target_link_libraries(rime_smoke PRIVATE lens_rime)
