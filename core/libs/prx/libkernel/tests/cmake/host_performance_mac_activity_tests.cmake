if(BUILD_TESTING)
    if(UNIX)
        add_test_executable(host_performance_mac_activity_tests
            ${LIBS_INCLUDE_DIR}/tests/HostPerformanceMacActivity.cpp
            ${CMAKE_CURRENT_SOURCE_DIR}/System/src/MacActivity.cpp)
        target_include_directories(host_performance_mac_activity_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(host_performance_mac_activity_tests PRIVATE ${CMAKE_DL_LIBS})
        set_target_properties(host_performance_mac_activity_tests PROPERTIES CXX_EXTENSIONS OFF)
        add_dependencies(host_performance_mac_activity_tests ${objcFixtureLibraries})
        add_test(NAME host_performance_mac_activity COMMAND host_performance_mac_activity_tests
            $<TARGET_FILE:objc_fixture> $<TARGET_FILE:objc_fixture_no_class>
            $<TARGET_FILE:objc_fixture_nil_activity> $<TARGET_FILE:objc_fixture_no_pool>
            ${CMAKE_CURRENT_BINARY_DIR}/no-such-libobjc.dylib)
        set_tests_properties(host_performance_mac_activity PROPERTIES TIMEOUT 20)
    endif()
endif()
