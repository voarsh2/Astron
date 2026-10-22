find_path(LIBUV_INCLUDE_DIR NAMES uv.h)
find_library(LIBUV_LIBRARY NAMES uv libuv uv_a)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(libuv
    REQUIRED_VARS LIBUV_INCLUDE_DIR LIBUV_LIBRARY
)

if(libuv_FOUND AND NOT TARGET libuv::libuv)
    add_library(libuv::libuv UNKNOWN IMPORTED)
    set_target_properties(libuv::libuv PROPERTIES
        IMPORTED_LOCATION "${LIBUV_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${LIBUV_INCLUDE_DIR}"
    )
endif()

mark_as_advanced(LIBUV_INCLUDE_DIR LIBUV_LIBRARY)
