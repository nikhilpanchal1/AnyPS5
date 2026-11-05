if(BUILD_TESTING)
    add_test_executable(guest_wait_trace_tests ${LIBS_INCLUDE_DIR}/tests/GuestWaitTrace.cpp)
    target_include_directories(guest_wait_trace_tests PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(guest_wait_trace_tests PRIVATE libkernel libc)
    configure_windows_unwind(guest_wait_trace_tests)
    add_test(NAME guest_wait_trace COMMAND guest_wait_trace_tests)
    set_tests_properties(guest_wait_trace PROPERTIES
        ENVIRONMENT "APS5_TRACE_WAITS=1"
        PASS_REGULAR_EXPRESSION "wait_trace_active_zero[^|]*x1"
        FAIL_REGULAR_EXPRESSION "wait_trace_inactive[^|]*x0"
        TIMEOUT 30)
    if(WIN32)
        set_tests_properties(guest_wait_trace PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
    endif()
endif()
