set(DC_PARSER_SOURCES)
set(DC_PARSER_INCLUDE_DIRS)

if(ASTRON_REGENERATE_DC_PARSER)
    set(DC_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
    file(MAKE_DIRECTORY "${DC_GENERATED_DIR}/file")

    BISON_TARGET(DCParser
        "${CMAKE_CURRENT_SOURCE_DIR}/file/parser.ypp"
        "${DC_GENERATED_DIR}/file/parser.cpp"
        DEFINES_FILE "${DC_GENERATED_DIR}/file/parser.h"
    )
    FLEX_TARGET(DCLexer
        "${CMAKE_CURRENT_SOURCE_DIR}/file/lexer.lpp"
        "${DC_GENERATED_DIR}/file/lexer.cpp"
    )
    ADD_FLEX_BISON_DEPENDENCY(DCLexer DCParser)

    list(APPEND DC_PARSER_SOURCES ${BISON_DCParser_OUTPUTS} ${FLEX_DCLexer_OUTPUTS})
    list(APPEND DC_PARSER_INCLUDE_DIRS "${DC_GENERATED_DIR}")
else()
    list(APPEND DC_PARSER_SOURCES file/parser.cpp file/lexer.cpp)
endif()

add_library(dclass
    util/PrimeNumberGenerator.cpp
    util/HashGenerator.cpp
    dc/DistributedType.cpp
    dc/NumericType.cpp
    dc/ArrayType.cpp
    dc/Struct.cpp
    dc/Class.cpp
    dc/Method.cpp
    dc/KeywordList.cpp
    dc/File.cpp
    dc/Field.cpp
    dc/MolecularField.cpp
    dc/Parameter.cpp
    ${DC_PARSER_SOURCES}
    file/write.cpp
    file/read.cpp
    file/hash_legacy.cpp
    value/format.cpp
    value/parse.cpp
    value/default.cpp
)

target_include_directories(dclass PUBLIC
    ${DC_PARSER_INCLUDE_DIRS}
    "${CMAKE_CURRENT_SOURCE_DIR}"
)

if(NOT MSVC)
    set_source_files_properties(${DC_PARSER_SOURCES} PROPERTIES COMPILE_OPTIONS "-Wno-sign-compare")
endif()
