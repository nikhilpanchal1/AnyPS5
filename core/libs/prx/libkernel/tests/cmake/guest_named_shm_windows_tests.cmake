if(BUILD_TESTING)
    if(WIN32)
        add_test_executable(guest_named_shm_windows_tests ${LIBS_INCLUDE_DIR}/tests/GuestNamedShmWindows.cpp)
        target_include_directories(guest_named_shm_windows_tests PRIVATE ${LIBS_INCLUDE_DIR} ${LIBS_INCLUDE_DIR}/nid/include)
        target_link_libraries(guest_named_shm_windows_tests PRIVATE libkernel libc advapi32)
        configure_windows_unwind(guest_named_shm_windows_tests)
        foreach(part IN ITEMS basic reuse resize_read resize_write)
            set(named_shm_suffix "_${part}")
            if(part STREQUAL "basic")
                set(named_shm_suffix "")
            endif()
            add_test(NAME guest_named_shm_windows${named_shm_suffix} COMMAND guest_named_shm_windows_tests --case ${part})
            add_test(NAME guest_named_shm_windows_short_temp${named_shm_suffix} COMMAND guest_named_shm_windows_tests --short-temp ${part})
            add_test(NAME guest_named_shm_windows_long_short_temp${named_shm_suffix} COMMAND guest_named_shm_windows_tests --long-short-temp ${part})
            set_tests_properties(guest_named_shm_windows${named_shm_suffix}
                guest_named_shm_windows_short_temp${named_shm_suffix} guest_named_shm_windows_long_short_temp${named_shm_suffix}
                PROPERTIES TIMEOUT 20 ENVIRONMENT_MODIFICATION "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>")
            set_tests_properties(guest_named_shm_windows_short_temp${named_shm_suffix} guest_named_shm_windows_long_short_temp${named_shm_suffix}
                PROPERTIES SKIP_RETURN_CODE 77)
            if(part STREQUAL "resize_write")
                set_tests_properties(guest_named_shm_windows${named_shm_suffix}
                    guest_named_shm_windows_short_temp${named_shm_suffix} guest_named_shm_windows_long_short_temp${named_shm_suffix}
                    PROPERTIES PROCESSORS 3)
            elseif(part STREQUAL "reuse" OR part STREQUAL "resize_read")
                set_tests_properties(guest_named_shm_windows${named_shm_suffix}
                    guest_named_shm_windows_short_temp${named_shm_suffix} guest_named_shm_windows_long_short_temp${named_shm_suffix}
                    PROPERTIES PROCESSORS 2)
            endif()
        endforeach()
    endif()
endif()
