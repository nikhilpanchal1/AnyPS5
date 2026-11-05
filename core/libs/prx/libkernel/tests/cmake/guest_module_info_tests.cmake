if(BUILD_TESTING)
    add_test_executable(guest_module_info_tests ${LIBS_INCLUDE_DIR}/tests/GuestModuleInfo.cpp)
    target_include_directories(guest_module_info_tests PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(guest_module_info_tests PRIVATE libkernel libc)
    configure_windows_unwind(guest_module_info_tests)
    add_dependencies(guest_module_info_tests guest_module_fixture)
    add_test(NAME guest_module_info COMMAND guest_module_info_tests $<TARGET_FILE_NAME:guest_module_fixture>)
    set_tests_properties(guest_module_info PROPERTIES
        WORKING_DIRECTORY "$<TARGET_FILE_DIR:guest_module_fixture>")
    if(WIN32)
        set_tests_properties(guest_module_info PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
    endif()
endif()
