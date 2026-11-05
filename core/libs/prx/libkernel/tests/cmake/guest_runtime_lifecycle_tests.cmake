if(BUILD_TESTING)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND Python3_Interpreter_FOUND AND ANYPS5_RELINKER_CLI)
        add_test_executable(guest_runtime_lifecycle_tests ${LIBS_INCLUDE_DIR}/tests/GuestRuntimeLifecycle.cpp)
        target_include_directories(guest_runtime_lifecycle_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(guest_runtime_lifecycle_tests PRIVATE libkernel libc ${CMAKE_DL_LIBS})
        set_target_properties(guest_runtime_lifecycle_tests PROPERTIES ENABLE_EXPORTS ON)
        add_dependencies(guest_runtime_lifecycle_tests relinker)
        add_test(NAME guest_runtime_lifecycle COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/core/relinker/relinker/tests/test_guest_runtime_lifecycle.py
            $<TARGET_FILE:relinker> $<TARGET_FILE:guest_runtime_lifecycle_tests> $<TARGET_FILE_DIR:libkernel>)
    endif()
endif()
