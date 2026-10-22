if(NOT DEFINED ASTRON_BUNDLE_EXECUTABLE OR NOT EXISTS "${ASTRON_BUNDLE_EXECUTABLE}")
    message(FATAL_ERROR "ASTRON_BUNDLE_EXECUTABLE must name an existing executable")
endif()

# This is a flat tarball, so place Homebrew libraries beside astrond instead of
# using the Frameworks directory expected for a conventional .app bundle.
function(gp_item_default_embedded_path_override item path_var)
    set(${path_var} "@executable_path" PARENT_SCOPE)
endfunction()

include(BundleUtilities)
fixup_bundle(
    "${ASTRON_BUNDLE_EXECUTABLE}"
    ""
    "${ASTRON_BUNDLE_SEARCH_DIRS}"
)
