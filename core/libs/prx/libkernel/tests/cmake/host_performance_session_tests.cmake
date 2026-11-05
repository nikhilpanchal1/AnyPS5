if(BUILD_TESTING)
    add_test_executable(host_performance_session_tests
        ${LIBS_INCLUDE_DIR}/tests/HostPerformanceSession.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostPerformance.cpp)
    target_include_directories(host_performance_session_tests PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(host_performance_session_tests PRIVATE Threads::Threads)
    set_target_properties(host_performance_session_tests PROPERTIES CXX_EXTENSIONS OFF)
    configure_host_test_executable(host_performance_session_tests)
    add_test(NAME host_performance_session COMMAND host_performance_session_tests)
    set_tests_properties(host_performance_session PROPERTIES TIMEOUT 20)
endif()
