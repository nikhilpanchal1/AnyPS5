if(BUILD_TESTING)
    add_test_executable(guest_dynamic_loader_variants_tests ${LIBS_INCLUDE_DIR}/tests/GuestDynamicLoaderVariants.cpp)
    target_include_directories(guest_dynamic_loader_variants_tests PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(guest_dynamic_loader_variants_tests PRIVATE libkernel libc)
    configure_windows_unwind(guest_dynamic_loader_variants_tests)
    add_dependencies(guest_dynamic_loader_variants_tests guest_module_fixture)
    add_test(NAME guest_dynamic_loader_variant_names COMMAND guest_dynamic_loader_variants_tests)
    set_tests_properties(guest_dynamic_loader_variant_names PROPERTIES TIMEOUT 15
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/variant_names")
    if(WIN32)
        set_tests_properties(guest_dynamic_loader_variant_names PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
    endif()
endif()
