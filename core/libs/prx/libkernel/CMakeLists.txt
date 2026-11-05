add_library(libkernel SHARED EXCLUDE_FROM_ALL
        ${CMAKE_CURRENT_SOURCE_DIR}/Unimplemented.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Apr/src/Apr.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Equeue/Equeue.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Equeue/src/EdgeWatch.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Equeue/src/EventAccessors.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/ArchivedFile.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/DescriptorControl.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Equeue/src/FileEvent.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Equeue/src/Kqueue.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/DirectoryDescriptor.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/FileLock.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/FilesystemForwards.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/NativeStat.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/Terminal.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/Open.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/OpenFileLimit.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/SharedMemory.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/RandomDevice.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/HostStreams.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/SandboxCertificates.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/File/src/Stdio.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/../libc/src/Rename.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Semaphore/src/Ksem.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Semaphore/src/Semaphore.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/SyncOnAddress/src/SyncOnAddress.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/DirectMemory/Export.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/DirectMemory/DirectMemory.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/DirectMemory/Jit.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/DirectMemory/PosixMemory.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/DirectMemory/MemoryPool.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/DirectMemory/MemoryPoolExport.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/Mutex.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/Cond.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/Attr.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/Thread.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/Tsd.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/GuestTlsMacOs.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/Rwlock.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/Sem.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/src/MainThreadMacOs.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Atfork.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Attr.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Barrier.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Cond.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Mutex.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Rwlock.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Thread.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Once.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Tsd.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Sem.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Pthread/Posix/Spinlock.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Socket/src/Pselect.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Socket/src/Socket.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Socket/src/Udp.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Socket/src/SocketOptions.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Socket/src/AddressConversion.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Socket/src/SocketConnect.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/EventFlag/src/EventFlag.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Module/src/Module.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Module/src/DynamicLoader.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Module/src/ModuleInfo.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Module/src/Tls.cpp
        ${LIBS_INCLUDE_DIR}/nid/src/NidCompute.cpp
        ${LIBS_INCLUDE_DIR}/nid/src/Sha1.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Aio/src/Aio.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Coredump.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Exception.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Sanitizer.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Rtld.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Process.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Sandbox.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostCpu.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostPerformance.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostPerformanceProcess.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/HostPerformanceStartup.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/MimallocMacOs.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/SystemConfiguration.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Login.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Getlogin.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/SoftwareVersion.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Error.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/ThermalSensors.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Signals.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/SigvecRegistration.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/SignalSets.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/Notification.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/System/src/UserContext.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Time/Ktimer.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Time/SleepWake.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Time/Time.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/Time/TimedWait.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/AppMetadata/src/AppMetadata.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/AppMetadata/src/ParamJsonParser.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/AppMetadata/src/ParamSfoParser.cpp
)
if(APPLE)
    target_link_libraries(libkernel PRIVATE "-framework CoreFoundation")
    target_sources(libkernel PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/System/src/MacActivity.cpp)
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_sources(libkernel PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/System/src/GameModeClient.cpp)
endif()

target_include_directories(libkernel PRIVATE ${LIBS_INCLUDE_DIR})
target_include_directories(libkernel PRIVATE ${LIBS_INCLUDE_DIR}/nid/include)
target_link_libraries(libkernel PRIVATE ${CMAKE_DL_LIBS})
target_link_libraries(libkernel PRIVATE libc)
if(WIN32)
    target_sources(libkernel PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/File/src/TrustedRoots.cpp)
    target_link_libraries(libkernel PRIVATE ws2_32 shell32 advapi32 crypt32 wbemuuid ole32 oleaut32)
    target_link_libraries(libkernel PRIVATE iphlpapi)
    target_compile_definitions(libkernel PRIVATE _WIN32_WINNT=0x0602)
endif()
configure_windows_unwind(libkernel)

if(BUILD_TESTING)
    add_library(guest_exec_host SHARED ${LIBS_INCLUDE_DIR}/tests/GuestExecHost.cpp)
    target_include_directories(guest_exec_host PRIVATE ${LIBS_INCLUDE_DIR})
    target_link_libraries(guest_exec_host PRIVATE libkernel libc libSceAgcDriver)
    set_target_properties(guest_exec_host PROPERTIES PREFIX "" SUFFIX ".prx" BUILD_RPATH "$ORIGIN")
    configure_windows_unwind(guest_exec_host)
    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_FOUND AND ANYPS5_RELINKER_CLI)
        add_test(NAME exec_arguments COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/core/relinker/relinker/tests/test_exec_arguments.py
            $<TARGET_FILE:relinker> $<TARGET_FILE:guest_exec_host>
            $<TARGET_FILE:libSceAgcDriver> $<TARGET_FILE:libc> $<TARGET_FILE:libkernel> ${CMAKE_CXX_COMPILER})
        set_tests_properties(exec_arguments PROPERTIES TIMEOUT 30)
        add_asan_test_options(exec_arguments verify_asan_link_order=0)
    endif()
    if(NOT WIN32)
        add_library(guest_memory_lifetime_module MODULE ${LIBS_INCLUDE_DIR}/tests/GuestMemoryLifetimeModule.cpp)
        target_include_directories(guest_memory_lifetime_module PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(guest_memory_lifetime_module PRIVATE libkernel libc)
    endif()
    find_package(Python3 QUIET COMPONENTS Interpreter)
    add_library(guest_module_fixture SHARED ${LIBS_INCLUDE_DIR}/tests/GuestModuleFixture.cpp)
    target_include_directories(guest_module_fixture PRIVATE ${LIBS_INCLUDE_DIR})
    add_custom_command(TARGET guest_module_fixture POST_BUILD
        COMMAND $<TARGET_FILE:nid_patcher> guest_module_fixture $<TARGET_FILE:guest_module_fixture>
        VERBATIM)
    add_dependencies(guest_module_fixture nid_patcher)
    configure_windows_unwind(guest_module_fixture)
    set_target_properties(guest_module_fixture PROPERTIES BUILD_WITH_INSTALL_RPATH ON INSTALL_RPATH "$ORIGIN")
    if(Python3_Interpreter_FOUND)
        if(NOT WIN32 AND NOT APPLE)
            target_link_options(guest_module_fixture PRIVATE -Wl,--no-as-needed)
            add_test(NAME nid_patcher_dynamic_strings COMMAND ${Python3_EXECUTABLE}
                ${LIBS_INCLUDE_DIR}/nid/tests/test_dynamic_strings.py $<TARGET_FILE:guest_module_fixture>)
        endif()
        add_test(NAME nid_patcher_symbol_versions COMMAND ${Python3_EXECUTABLE}
            ${LIBS_INCLUDE_DIR}/nid/tests/test_symbol_versions.py $<TARGET_FILE:nid_patcher>)
    endif()
    if(WIN32)
        file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/GuestDynamicLoader.def" CONTENT "EXPORTS\nGuestDefaultScopeOnly\n")
    endif()
    if(WIN32)
        enable_language(ASM)
        add_library(guest_deferred_module_fixture SHARED
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredModuleFixture.cpp
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredModuleFixture.S)
        target_include_directories(guest_deferred_module_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_options(guest_deferred_module_fixture PRIVATE -Wl,--image-base,0x38000000 -Wl,--disable-dynamicbase)
        configure_windows_unwind(guest_deferred_module_fixture)
        set_target_properties(guest_deferred_module_fixture PROPERTIES PREFIX "" SUFFIX ".guest.prx")
        add_library(guest_deferred_dependent_fixture SHARED
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredModuleFixture.cpp
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredDependentFixture.S)
        target_include_directories(guest_deferred_dependent_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        target_compile_definitions(guest_deferred_dependent_fixture PRIVATE GUEST_DEFERRED_DEPENDENT_FIXTURE=1)
        target_link_options(guest_deferred_dependent_fixture PRIVATE -Wl,--image-base,0x39000000 -Wl,--disable-dynamicbase)
        configure_windows_unwind(guest_deferred_dependent_fixture)
        set_target_properties(guest_deferred_dependent_fixture PROPERTIES PREFIX "" SUFFIX ".guest.prx")
        add_library(guest_deferred_sweep_fixture SHARED
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredModuleFixture.cpp
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredSweepFixture.S)
        target_include_directories(guest_deferred_sweep_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        target_compile_definitions(guest_deferred_sweep_fixture PRIVATE GUEST_DEFERRED_DEPENDENT_FIXTURE=1)
        target_link_options(guest_deferred_sweep_fixture PRIVATE -Wl,--image-base,0x3a000000 -Wl,--disable-dynamicbase)
        configure_windows_unwind(guest_deferred_sweep_fixture)
        set_target_properties(guest_deferred_sweep_fixture PROPERTIES PREFIX "" SUFFIX ".guest.prx")
        add_library(guest_deferred_failed_fixture SHARED
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredModuleFixture.cpp
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredFailedFixture.S)
        target_include_directories(guest_deferred_failed_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_options(guest_deferred_failed_fixture PRIVATE -Wl,--image-base,0x3b000000 -Wl,--disable-dynamicbase)
        configure_windows_unwind(guest_deferred_failed_fixture)
        set_target_properties(guest_deferred_failed_fixture PROPERTIES PREFIX "" SUFFIX ".guest.prx")
        add_library(guest_deferred_sweep_failed_fixture SHARED
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredModuleFixture.cpp
            ${LIBS_INCLUDE_DIR}/tests/GuestDeferredSweepFailedFixture.S)
        target_include_directories(guest_deferred_sweep_failed_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        target_compile_definitions(guest_deferred_sweep_failed_fixture PRIVATE GUEST_DEFERRED_DEPENDENT_FIXTURE=1)
        target_link_options(guest_deferred_sweep_failed_fixture PRIVATE -Wl,--image-base,0x3c000000 -Wl,--disable-dynamicbase)
        configure_windows_unwind(guest_deferred_sweep_failed_fixture)
        set_target_properties(guest_deferred_sweep_failed_fixture PROPERTIES PREFIX "" SUFFIX ".guest.prx")
    endif()
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/variant_names")
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/variant_names/guest_module_fixture.sprx.GUEST.PRX" "not a module\n")
    add_custom_command(TARGET guest_module_fixture POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy "$<TARGET_FILE:guest_module_fixture>"
            "${CMAKE_CURRENT_BINARY_DIR}/variant_names/guest_module_fixture.elf.GUEST.PRX"
        VERBATIM)
    if(NOT WIN32)
        add_custom_command(TARGET guest_module_fixture POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E create_symlink missing.guest.prx
                "${CMAKE_CURRENT_BINARY_DIR}/variant_names/guest_module_fixture.zprx.GUEST.PRX"
            VERBATIM)
    endif()

    if(Python3_Interpreter_FOUND)
        find_package(Threads REQUIRED)
    endif()

    if(WIN32)
        add_library(guest_unwind_module_info_fixture SHARED ${LIBS_INCLUDE_DIR}/tests/GuestUnwindModuleInfoFixture.cpp)
        target_include_directories(guest_unwind_module_info_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        target_compile_options(guest_unwind_module_info_fixture PRIVATE -fno-exceptions)
        add_test_executable(guest_unwind_module_info_tests ${LIBS_INCLUDE_DIR}/tests/GuestUnwindModuleInfo.cpp)
        target_include_directories(guest_unwind_module_info_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(guest_unwind_module_info_tests PRIVATE libkernel libc guest_unwind_module_info_fixture)
        configure_windows_unwind(guest_unwind_module_info_tests)
        add_test(NAME guest_unwind_module_info COMMAND guest_unwind_module_info_tests)
        set_tests_properties(guest_unwind_module_info PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:libkernel>;PATH=path_list_prepend:$<TARGET_FILE_DIR:guest_unwind_module_info_fixture>")
    elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        add_library(guest_unwind_module_info_fixture SHARED ${LIBS_INCLUDE_DIR}/tests/GuestModuleFixture.cpp)
        target_include_directories(guest_unwind_module_info_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        set_target_properties(guest_unwind_module_info_fixture PROPERTIES PREFIX "" OUTPUT_NAME guest_unwind_module_info_fixture.prx SUFFIX ".guest.prx")
        add_library(guest_unwind_no_header_fixture SHARED ${LIBS_INCLUDE_DIR}/tests/GuestModuleFixture.cpp)
        target_include_directories(guest_unwind_no_header_fixture PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_options(guest_unwind_no_header_fixture PRIVATE -Wl,--no-eh-frame-hdr)
        set_target_properties(guest_unwind_no_header_fixture PROPERTIES PREFIX "" OUTPUT_NAME guest_unwind_no_header_fixture.prx SUFFIX ".guest.prx")
        add_test_executable(guest_unwind_module_info_tests ${LIBS_INCLUDE_DIR}/tests/GuestUnwindModuleInfoLinux.cpp)
        target_include_directories(guest_unwind_module_info_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(guest_unwind_module_info_tests PRIVATE libkernel libc)
        add_dependencies(guest_unwind_module_info_tests guest_unwind_module_info_fixture guest_unwind_no_header_fixture)
        add_test(NAME guest_unwind_module_info COMMAND guest_unwind_module_info_tests guest_unwind_module_info_fixture.prx guest_unwind_no_header_fixture.prx)
        set_tests_properties(guest_unwind_module_info PROPERTIES
            WORKING_DIRECTORY "$<TARGET_FILE_DIR:guest_unwind_module_info_fixture>")
        add_test_executable(guest_unwind_module_info_failure_tests ${LIBS_INCLUDE_DIR}/tests/GuestUnwindModuleInfoFailureLinux.cpp)
        target_include_directories(guest_unwind_module_info_failure_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(guest_unwind_module_info_failure_tests PRIVATE libkernel libc)
        set_target_properties(guest_unwind_module_info_failure_tests PROPERTIES ENABLE_EXPORTS ON)
        add_test(NAME guest_unwind_module_info_failure COMMAND guest_unwind_module_info_failure_tests)
    elseif(APPLE)
        add_test_executable(guest_unwind_module_info_tests ${LIBS_INCLUDE_DIR}/tests/GuestUnwindModuleInfoMacos.cpp)
        target_include_directories(guest_unwind_module_info_tests PRIVATE ${LIBS_INCLUDE_DIR})
        target_link_libraries(guest_unwind_module_info_tests PRIVATE libkernel libc)
        add_test(NAME guest_unwind_module_info COMMAND guest_unwind_module_info_tests)
    endif()
    add_library(guest_memory_module SHARED ${LIBS_INCLUDE_DIR}/tests/GuestMemoryModule.cpp)
    set_target_properties(guest_memory_module PROPERTIES PREFIX "" SUFFIX ".guest.prx")
    if(WIN32)
        add_library(guest_memory_elf0_module SHARED
            ${LIBS_INCLUDE_DIR}/tests/GuestMemoryModule.cpp
            ${LIBS_INCLUDE_DIR}/tests/GuestMemoryModule.S)
        set_target_properties(guest_memory_elf0_module PROPERTIES PREFIX "" SUFFIX ".guest.prx")
    endif()
    add_library(guest_flexible_memory_module SHARED ${LIBS_INCLUDE_DIR}/tests/GuestFlexibleMemoryModule.cpp)
    target_include_directories(guest_flexible_memory_module PRIVATE ${LIBS_INCLUDE_DIR})
    set_target_properties(guest_flexible_memory_module PROPERTIES PREFIX "" SUFFIX ".guest.prx")
endif()

if(BUILD_TESTING)
    find_package(Threads REQUIRED)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        add_library(game_mode_fixture SHARED ${LIBS_INCLUDE_DIR}/tests/GameModeFixtureLibrary.cpp)
        add_library(game_mode_fixture_no_end SHARED ${LIBS_INCLUDE_DIR}/tests/GameModeFixtureLibrary.cpp)
        target_compile_definitions(game_mode_fixture_no_end PRIVATE FIXTURE_OMIT_END)
        add_library(game_mode_fixture_no_error_string SHARED ${LIBS_INCLUDE_DIR}/tests/GameModeFixtureLibrary.cpp)
        target_compile_definitions(game_mode_fixture_no_error_string PRIVATE FIXTURE_OMIT_ERROR_STRING)
        set_target_properties(game_mode_fixture game_mode_fixture_no_end game_mode_fixture_no_error_string PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY "${ANYPS5_TEST_OUTPUT_DIRECTORY}")
    endif()
    if(UNIX)
        set(objcFixtureLibraries "")
        foreach(objcFixture IN ITEMS objc_fixture:FIXTURE_COMPLETE objc_fixture_no_class:FIXTURE_NO_CLASS objc_fixture_nil_activity:FIXTURE_NIL_ACTIVITY objc_fixture_no_pool:FIXTURE_OMIT_POOL)
            string(REPLACE ":" ";" objcFixture ${objcFixture})
            list(GET objcFixture 0 objcFixtureName)
            add_library(${objcFixtureName} SHARED ${LIBS_INCLUDE_DIR}/tests/ObjcFixtureLibrary.cpp)
            set_target_properties(${objcFixtureName} PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${ANYPS5_TEST_OUTPUT_DIRECTORY}")
            list(GET objcFixture 1 objcFixtureDefinition)
            target_compile_definitions(${objcFixtureName} PRIVATE ${objcFixtureDefinition})
            list(APPEND objcFixtureLibraries ${objcFixtureName})
        endforeach()
    endif()
    function(add_host_performance_process_test name pattern)
        add_test(NAME host_performance_process_${name} COMMAND host_performance_process_tests ${ARGN})
        set_tests_properties(host_performance_process_${name} PROPERTIES TIMEOUT 20 PASS_REGULAR_EXPRESSION "${pattern}")
        if(WIN32)
            set_tests_properties(host_performance_process_${name} PROPERTIES ENVIRONMENT_MODIFICATION
                "PATH=path_list_prepend:$<TARGET_FILE_DIR:libc>")
        endif()
    endfunction()
    add_host_performance_process_test(exit "begin called.release ran at exit" exit)
    add_host_performance_process_test(exit_without_handlers "begin called.release ran at exit" exit-without-handlers)
    add_host_performance_process_test(refused "begin called" refused)
    set_tests_properties(host_performance_process_refused PROPERTIES FAIL_REGULAR_EXPRESSION "release ran")
    add_host_performance_process_test(off "off left the backend alone" off)
    set_tests_properties(host_performance_process_off PROPERTIES FAIL_REGULAR_EXPRESSION "begin called")
    add_host_performance_process_test(twice "second session refused" twice)
    add_host_performance_process_test(environment "environment accepted" environment)
endif()

file(GLOB kernelTestFragments CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/tests/cmake/*.cmake)
list(SORT kernelTestFragments)
foreach(kernelTestFragment IN LISTS kernelTestFragments)
    include(${kernelTestFragment})
endforeach()
