if(BUILD_TESTING)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        add_test_executable(host_performance_game_mode_tests
            ${LIBS_INCLUDE_DIR}/tests/HostPerformanceGameMode.cpp
            ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostPerformance.cpp
            ${CMAKE_CURRENT_SOURCE_DIR}/System/src/GameModeClient.cpp)
        target_include_directories(host_performance_game_mode_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(host_performance_game_mode_tests PRIVATE ${CMAKE_DL_LIBS})
        set_target_properties(host_performance_game_mode_tests PROPERTIES CXX_EXTENSIONS OFF)
        add_dependencies(host_performance_game_mode_tests game_mode_fixture game_mode_fixture_no_end game_mode_fixture_no_error_string)
        add_test(NAME host_performance_game_mode COMMAND host_performance_game_mode_tests
            $<TARGET_FILE:game_mode_fixture> $<TARGET_FILE:game_mode_fixture_no_end>
            $<TARGET_FILE:game_mode_fixture_no_error_string>
            ${CMAKE_CURRENT_BINARY_DIR}/no-such-libgamemode.so)
        set_tests_properties(host_performance_game_mode PROPERTIES TIMEOUT 20)
    endif()
endif()
