if(BUILD_TESTING)
    if(Python3_Interpreter_FOUND)
        add_test_executable(semaphore_trace_tests
            ${LIBS_INCLUDE_DIR}/tests/SemaphoreTrace.cpp
            ${CMAKE_CURRENT_SOURCE_DIR}/Semaphore/src/Semaphore.cpp
            ${CMAKE_CURRENT_SOURCE_DIR}/Time/TimedWait.cpp)
        target_include_directories(semaphore_trace_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(semaphore_trace_tests PRIVATE Threads::Threads libc)
    endif()
endif()
