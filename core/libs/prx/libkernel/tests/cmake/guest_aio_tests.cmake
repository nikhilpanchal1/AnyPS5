if(BUILD_TESTING)
    add_test_executable(guest_aio_tests ${LIBS_INCLUDE_DIR}/tests/GuestAio.cpp)
    target_include_directories(guest_aio_tests PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(guest_aio_tests PRIVATE libkernel libc)
    configure_windows_unwind(guest_aio_tests)
    add_test(NAME guest_aio COMMAND guest_aio_tests)
    if(WIN32)
        add_test(NAME guest_aio_bad_descriptors COMMAND guest_aio_tests bad-descriptors)
        set_tests_properties(guest_aio_bad_descriptors PROPERTIES TIMEOUT 20 ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
        set_tests_properties(guest_aio PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
    endif()
endif()
