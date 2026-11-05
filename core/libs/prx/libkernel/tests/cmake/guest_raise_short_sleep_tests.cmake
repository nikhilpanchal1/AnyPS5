if(BUILD_TESTING)
    if(WIN32)
        add_test_executable(guest_raise_short_sleep_tests ${LIBS_INCLUDE_DIR}/tests/GuestRaiseShortSleep.cpp)
        target_include_directories(guest_raise_short_sleep_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(guest_raise_short_sleep_tests PRIVATE libkernel libc)
        configure_windows_unwind(guest_raise_short_sleep_tests)
        add_test(NAME guest_raise_short_sleep COMMAND guest_raise_short_sleep_tests)
        set_tests_properties(guest_raise_short_sleep PROPERTIES TIMEOUT 30 ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
        add_test(NAME guest_raise_short_sleep_without_wake COMMAND guest_raise_short_sleep_tests)
        set_tests_properties(guest_raise_short_sleep_without_wake PROPERTIES TIMEOUT 30 ENVIRONMENT "APS5_NO_SLEEP_WAKE=1" ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
    endif()
endif()
