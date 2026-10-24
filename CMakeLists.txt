cmake_minimum_required(VERSION 3.18)

project(Astron LANGUAGES C CXX)

include(GNUInstallDirs)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set_property(GLOBAL PROPERTY USE_FOLDERS ON)

if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "Build type")
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS RelWithDebInfo Release Debug)
endif()

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake/modules")

if(WIN32)
    set(ASTRON_REGENERATE_DC_PARSER_DEFAULT OFF)
else()
    set(ASTRON_REGENERATE_DC_PARSER_DEFAULT ON)
endif()
option(ASTRON_REGENERATE_DC_PARSER "Regenerate the DC parser with Flex and Bison in the build directory" ${ASTRON_REGENERATE_DC_PARSER_DEFAULT})
option(ASTRON_ENABLE_INTEGRATION_TESTS "Register the Python integration tests with CTest" OFF)
option(STATIC_ASTRON "Attempt to statically link Astron (experimental)" OFF)
option(USE_32BIT_DATAGRAMS "Use 32-bit datagram and dclass size tags" OFF)
option(USE_128BIT_CHANNELS "Use 128-bit channels and 64-bit doids/zones" OFF)
option(BUILD_TESTS "Compile the internal C++ daemon tests" OFF)

option(BUILD_DBSERVER "Build the Database Server" ON)
option(BUILD_DB_YAML "Build the YAML database backend" ON)
option(BUILD_DB_POSTGRESQL "Build the PostgreSQL database backend" OFF)
option(BUILD_DB_MYSQL "Build the MySQL database backend" OFF)
option(BUILD_DB_SQLITE "Build the SQLite database backend" OFF)
option(BUILD_DB_MONGO "Build the MongoDB database backend" OFF)
option(BUILD_STATESERVER "Build the State Server" ON)
option(BUILD_STATESERVER_DBSS "Build Database-State Server support" ON)
option(BUILD_EVENTLOGGER "Build the Event Logger" ON)
option(BUILD_CLIENTAGENT "Build the Client Agent" ON)

if(NOT BUILD_DBSERVER)
    set(BUILD_DB_YAML OFF)
    set(BUILD_DB_POSTGRESQL OFF)
    set(BUILD_DB_MYSQL OFF)
    set(BUILD_DB_SQLITE OFF)
    set(BUILD_DB_MONGO OFF)
endif()

if(STATIC_ASTRON)
    message(FATAL_ERROR "STATIC_ASTRON is not supported by the current dependency set")
endif()

if(ASTRON_ENABLE_INTEGRATION_TESTS)
    find_package(Python3 3.8 REQUIRED COMPONENTS Interpreter)
    enable_testing()
endif()

find_package(Boost REQUIRED)
find_package(yaml-cpp CONFIG REQUIRED)
find_package(libuv REQUIRED)
find_package(Threads REQUIRED)

if(TARGET yaml-cpp::yaml-cpp)
    set(ASTRON_YAML_TARGET yaml-cpp::yaml-cpp)
elseif(TARGET yaml-cpp)
    set(ASTRON_YAML_TARGET yaml-cpp)
else()
    message(FATAL_ERROR "yaml-cpp was found, but it did not export a supported CMake target")
endif()

if(ASTRON_REGENERATE_DC_PARSER)
    find_package(BISON 3.0 REQUIRED)
    find_package(FLEX 2.6 REQUIRED)
endif()

set(CORE_FILES
    src/core/global.h
    src/core/global.cpp
    src/core/main.cpp
    src/core/Logger.h
    src/core/Logger.cpp
    src/core/Role.h
    src/core/Role.cpp
    src/core/RoleFactory.h
    src/core/RoleFactory.cpp
    src/core/shutdown.h
    src/core/shutdown.cpp
    src/core/types.h
    src/core/msgtypes.h
)

set(CONFIG_FILES
    src/config/ConfigGroup.h
    src/config/ConfigGroup.cpp
    src/config/ConfigVariable.h
    src/config/ConfigVariable.cpp
    src/config/constraints.cpp
)

set(MESSAGEDIRECTOR_FILES
    src/messagedirector/ChannelMap.cpp
    src/messagedirector/ChannelMap.h
    src/messagedirector/MessageDirector.cpp
    src/messagedirector/MessageDirector.h
    src/messagedirector/MDNetworkParticipant.cpp
    src/messagedirector/MDNetworkParticipant.h
    src/messagedirector/MDNetworkUpstream.cpp
    src/messagedirector/MDNetworkUpstream.h
)

set(UTIL_FILES
    src/util/Datagram.h
    src/util/DatagramIterator.h
    src/util/EventSender.cpp
    src/util/EventSender.h
    src/util/IntegrationTestHooks.cpp
    src/util/IntegrationTestHooks.h
    src/util/Timeout.cpp
    src/util/Timeout.h
    src/util/TaskQueue.cpp
    src/util/TaskQueue.h
)

set(NET_FILES
    src/net/address_utils.cpp
    src/net/address_utils.h
    src/net/HAProxyHandler.cpp
    src/net/HAProxyHandler.h
    src/net/NetworkAcceptor.cpp
    src/net/NetworkAcceptor.h
    src/net/NetworkClient.cpp
    src/net/NetworkClient.h
    src/net/NetworkConnector.cpp
    src/net/NetworkConnector.h
    src/net/TcpAcceptor.cpp
    src/net/TcpAcceptor.h
)

set(ASTRON_SOURCES
    ${CORE_FILES}
    ${CONFIG_FILES}
    ${MESSAGEDIRECTOR_FILES}
    ${UTIL_FILES}
    ${NET_FILES}
)
set(ASTRON_DB_LIBRARIES)

if(BUILD_DBSERVER)
    list(APPEND ASTRON_SOURCES
        src/database/DatabaseServer.h
        src/database/DatabaseServer.cpp
        src/database/DatabaseBackend.h
        src/database/DatabaseBackend.cpp
        src/database/DBOperation.h
        src/database/DBOperation.cpp
        src/database/DBOperationQueue.h
        src/database/DBOperationQueue.cpp
        src/database/OldDatabaseBackend.h
        src/database/OldDatabaseBackend.cpp
        src/database/DBBackendFactory.h
        src/database/DBBackendFactory.cpp
    )

    if(BUILD_DB_YAML)
        list(APPEND ASTRON_SOURCES src/database/YAMLDatabase.cpp)
    endif()

    if(BUILD_DB_MONGO)
        find_package(mongocxx 4.4 CONFIG REQUIRED)

        if(TARGET mongo::mongocxx_shared AND TARGET mongo::bsoncxx_shared)
            list(APPEND ASTRON_DB_LIBRARIES mongo::mongocxx_shared mongo::bsoncxx_shared)
        elseif(TARGET mongo::mongocxx_static AND TARGET mongo::bsoncxx_static)
            list(APPEND ASTRON_DB_LIBRARIES mongo::mongocxx_static mongo::bsoncxx_static)
        else()
            message(FATAL_ERROR "MongoDB C++ driver was found, but it did not export supported CMake targets")
        endif()

        list(APPEND ASTRON_SOURCES src/database/MongoDatabase.cpp)
    endif()

    if(BUILD_DB_POSTGRESQL OR BUILD_DB_MYSQL OR BUILD_DB_SQLITE)
        find_package(SOCI 4 REQUIRED)
        if(NOT TARGET SOCI::SOCI)
            message(FATAL_ERROR "SOCI was found but did not export SOCI::SOCI")
        endif()
        list(APPEND ASTRON_DB_LIBRARIES SOCI::SOCI ${CMAKE_DL_LIBS})
        list(APPEND ASTRON_SOURCES src/database/SociSQLDatabase.cpp)
    endif()

    if(BUILD_DB_POSTGRESQL)
        find_package(PostgreSQL REQUIRED)
        find_library(SOCI_POSTGRESQL_PLUGIN NAMES soci_postgresql REQUIRED)
        list(APPEND ASTRON_DB_LIBRARIES PostgreSQL::PostgreSQL "${SOCI_POSTGRESQL_PLUGIN}")
    endif()

    if(BUILD_DB_MYSQL)
        find_library(SOCI_MYSQL_PLUGIN NAMES soci_mysql REQUIRED)
        list(APPEND ASTRON_DB_LIBRARIES "${SOCI_MYSQL_PLUGIN}")
    endif()

    if(BUILD_DB_SQLITE)
        find_library(SOCI_SQLITE3_PLUGIN NAMES soci_sqlite3 REQUIRED)
        list(APPEND ASTRON_DB_LIBRARIES "${SOCI_SQLITE3_PLUGIN}")
    endif()
endif()

if(BUILD_STATESERVER)
    list(APPEND ASTRON_SOURCES
        src/stateserver/StateServer.cpp
        src/stateserver/StateServer.h
        src/stateserver/DistributedObject.cpp
        src/stateserver/DistributedObject.h
    )
    if(BUILD_STATESERVER_DBSS)
        list(APPEND ASTRON_SOURCES
            src/stateserver/DBStateServer.cpp
            src/stateserver/DBStateServer.h
            src/stateserver/LoadingObject.cpp
            src/stateserver/LoadingObject.h
        )
    endif()
else()
    set(BUILD_STATESERVER_DBSS OFF)
endif()

if(BUILD_EVENTLOGGER)
    list(APPEND ASTRON_SOURCES
        src/eventlogger/EventLogger.cpp
        src/eventlogger/EventLogger.h
    )
endif()

if(BUILD_CLIENTAGENT)
    list(APPEND ASTRON_SOURCES
        src/clientagent/Client.h
        src/clientagent/Client.cpp
        src/clientagent/ClientAgent.h
        src/clientagent/ClientAgent.cpp
        src/clientagent/ClientMessages.h
        src/clientagent/ClientFactory.cpp
        src/clientagent/ClientFactory.h
        src/clientagent/AstronClient.cpp
    )
endif()

if(BUILD_TESTS)
    list(APPEND ASTRON_SOURCES
        src/tests/MDParticipantTest.cpp
        src/tests/MDPerformanceTest.cpp
    )
endif()

add_subdirectory(src/dclass)

add_executable(astrond ${ASTRON_SOURCES})
target_include_directories(astrond PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(astrond PRIVATE
    dclass
    "${ASTRON_YAML_TARGET}"
    Boost::boost
    libuv::libuv
    Threads::Threads
    ${ASTRON_DB_LIBRARIES}
)

target_compile_definitions(astrond PRIVATE ASTRON_WITH_YAML)
if(ASTRON_ENABLE_INTEGRATION_TESTS)
    target_compile_definitions(astrond PRIVATE ASTRON_ENABLE_INTEGRATION_TEST_HOOKS)
endif()
if(BUILD_DBSERVER)
    target_compile_definitions(astrond PRIVATE BUILD_DBSERVER)
endif()
if(BUILD_DB_YAML)
    target_compile_definitions(astrond PRIVATE BUILD_DB_YAML)
endif()
if(BUILD_DB_POSTGRESQL OR BUILD_DB_MYSQL OR BUILD_DB_SQLITE)
    target_compile_definitions(astrond PRIVATE BUILD_DB_SQL)
endif()
if(BUILD_STATESERVER)
    target_compile_definitions(astrond PRIVATE BUILD_STATESERVER)
endif()
if(BUILD_STATESERVER_DBSS)
    target_compile_definitions(astrond PRIVATE BUILD_STATESERVER_DBSS)
endif()
if(BUILD_EVENTLOGGER)
    target_compile_definitions(astrond PRIVATE BUILD_EVENTLOGGER)
endif()
if(BUILD_CLIENTAGENT)
    target_compile_definitions(astrond PRIVATE BUILD_CLIENTAGENT)
endif()
if(USE_32BIT_DATAGRAMS)
    target_compile_definitions(astrond PRIVATE ASTRON_32BIT_DATAGRAMS DCLASS_32BIT_SIZETAG)
endif()
if(USE_128BIT_CHANNELS)
    target_compile_definitions(astrond PRIVATE ASTRON_128BIT_CHANNELS)
endif()

if(ASTRON_GIT_SHA)
    set(GIT_SHA_VERSION "${ASTRON_GIT_SHA}")
else()
    find_package(Git QUIET)
    if(GIT_FOUND AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.git")
        execute_process(
            COMMAND "${GIT_EXECUTABLE}" describe --abbrev=8 --dirty --always
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            OUTPUT_VARIABLE GIT_SHA_VERSION
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )
    endif()
endif()
if(GIT_SHA_VERSION)
    target_compile_definitions(astrond PRIVATE "GIT_SHA1=\"${GIT_SHA_VERSION}\"")
endif()

target_compile_definitions(astrond PRIVATE "$<$<CONFIG:Debug>:ASTRON_DEBUG_MESSAGES>")

if(MSVC)
    target_compile_definitions(astrond PRIVATE WIN32_LEAN_AND_MEAN _WIN32_WINDOWS _WIN32_WINNT=0x0600 NOMINMAX _CRT_SECURE_NO_WARNINGS _WINSOCK_DEPRECATED_NO_WARNINGS)
    target_link_libraries(astrond PRIVATE wsock32 ws2_32)
    target_compile_options(astrond PRIVATE /W4)
else()
    target_compile_options(astrond PRIVATE -Wall -Wextra -Wno-error=deprecated-declarations)
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        target_compile_options(astrond PRIVATE -Wno-error=deprecated-register)
    endif()
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        target_link_libraries(astrond PRIVATE rt)
    endif()
endif()

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(dclass PRIVATE -Wall -Wextra -Wno-error=deprecated-declarations)
endif()
target_compile_definitions(dclass PUBLIC ASTRON_WITH_YAML)
if(USE_32BIT_DATAGRAMS)
    target_compile_definitions(dclass PUBLIC ASTRON_32BIT_DATAGRAMS DCLASS_32BIT_SIZETAG)
endif()
if(USE_128BIT_CHANNELS)
    target_compile_definitions(dclass PUBLIC ASTRON_128BIT_CHANNELS)
endif()

install(TARGETS astrond RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")

if(ASTRON_ENABLE_INTEGRATION_TESTS)
    add_executable(test_datagram_safety test/test_datagram_safety.cpp)
    target_include_directories(test_datagram_safety PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    target_link_libraries(test_datagram_safety PRIVATE dclass)

    add_test(NAME datagram_safety COMMAND test_datagram_safety)

    add_executable(test_historical_objects test/test_historical_objects.cpp)
    target_include_directories(test_historical_objects PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    target_link_libraries(test_historical_objects PRIVATE dclass)
    add_test(NAME historical_objects COMMAND test_historical_objects)

    if(BUILD_DB_MONGO)
        add_executable(astron_mongo_test_cleanup test/mongo_test_cleanup.cpp)
        target_link_libraries(astron_mongo_test_cleanup PRIVATE ${ASTRON_MONGO_LIBRARIES})
    endif()

    set(ASTRON_PYTHON_TESTS)
    function(astron_add_python_test name script)
        add_test(NAME "${name}"
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test/${script}")
        set_tests_properties("${name}" PROPERTIES WORKING_DIRECTORY "$<TARGET_FILE_DIR:astrond>")
        set(ASTRON_PYTHON_TESTS ${ASTRON_PYTHON_TESTS} "${name}" PARENT_SCOPE)
    endfunction()

    if(BUILD_DB_YAML)
        astron_add_python_test(db_yaml test_dbserver_yaml.py)
        astron_add_python_test(validate_config_dbyaml test_config_dbyaml.py)
    endif()
    if(BUILD_DB_MONGO)
        astron_add_python_test(db_mongo test_dbserver_mongodb.py)
        astron_add_python_test(validate_config_dbmongo test_config_dbmongo.py)
    endif()
    if(BUILD_DB_POSTGRESQL)
        astron_add_python_test(db_postgresql test_dbserver_postgres.py)
        astron_add_python_test(validate_config_dbpostgres test_config_dbpostgres.py)
    endif()
    if(BUILD_STATESERVER)
        astron_add_python_test(stateserver test_stateserver.py)
        astron_add_python_test(validate_config_stateserver test_config_stateserver.py)
        if(BUILD_STATESERVER_DBSS)
            astron_add_python_test(dbss test_dbss.py)
            astron_add_python_test(validate_config_dbss test_config_dbss.py)
        endif()
    endif()
    if(BUILD_EVENTLOGGER)
        astron_add_python_test(eventlogger test_eventlogger.py)
        astron_add_python_test(validate_config_eventlogger test_config_eventlogger.py)
    endif()
    if(BUILD_CLIENTAGENT)
        astron_add_python_test(clientagent test_clientagent.py)
        astron_add_python_test(clientagent_pending_object test_clientagent_pending_object.py)
        astron_add_python_test(issue_427 test_issue_427.py)
        astron_add_python_test(validate_config_clientagent test_config_clientagent.py)
    endif()
    astron_add_python_test(validate_config_core test_config.py)
    astron_add_python_test(messagedirector test_messagedirector.py)
    astron_add_python_test(messagedirector_write_queue test_messagedirector_write_queue.py)

    set(ASTRON_TEST_ENV)
    if(USE_32BIT_DATAGRAMS)
        list(APPEND ASTRON_TEST_ENV "USE_32BIT_DATAGRAMS=true")
    endif()
    if(USE_128BIT_CHANNELS)
        list(APPEND ASTRON_TEST_ENV "USE_128BIT_CHANNELS=true")
    endif()
    if(ASTRON_TEST_ENV)
        set_tests_properties(${ASTRON_PYTHON_TESTS} PROPERTIES ENVIRONMENT "${ASTRON_TEST_ENV}")
    endif()
endif()
