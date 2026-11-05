if(BUILD_TESTING)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        add_test_executable(guest_getlogin_no_session_tests
            ${LIBS_INCLUDE_DIR}/tests/GuestGetloginNoSession.cpp
            System/src/Login.cpp)
        target_include_directories(guest_getlogin_no_session_tests PRIVATE ${LIBS_INCLUDE_DIR})
        add_test(NAME guest_getlogin_no_session COMMAND guest_getlogin_no_session_tests)
        set_tests_properties(guest_getlogin_no_session PROPERTIES TIMEOUT 20)
    endif()
endif()
