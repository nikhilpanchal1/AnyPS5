if(BUILD_TESTING)
    add_test_executable(host_performance_process_tests
        ${LIBS_INCLUDE_DIR}/tests/HostPerformanceProcess.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostPerformance.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostPerformanceProcess.cpp)
    target_include_directories(host_performance_process_tests PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(host_performance_process_tests PRIVATE libc Threads::Threads ${CMAKE_DL_LIBS})
    set_target_properties(host_performance_process_tests PROPERTIES CXX_EXTENSIONS OFF)
    configure_windows_unwind(host_performance_process_tests)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        target_sources(host_performance_process_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/System/src/GameModeClient.cpp)
    elseif(APPLE)
        target_sources(host_performance_process_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/System/src/MacActivity.cpp)
    endif()
    add_test(NAME host_performance_process_invalid COMMAND host_performance_process_tests environment)
    set_tests_properties(host_performance_process_invalid PROPERTIES TIMEOUT 20 ENVIRONMENT "APS5_GAME_MODE=bogus"
        PASS_REGULAR_EXPRESSION "invalid value rejected by name")
    if(WIN32)
        set_tests_properties(host_performance_process_invalid PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libc>")
    endif()
endif()
