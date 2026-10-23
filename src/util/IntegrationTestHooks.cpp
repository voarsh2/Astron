#include "IntegrationTestHooks.h"
#include "core/global.h"

#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#endif

#include <utility>

void IntegrationTestHooks::run_after_interest_timeout_setup(
    std::function<void()> continuation)
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    const char* release_value = std::getenv(
        "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RELEASE_FILE");
    if(release_value != nullptr && *release_value != '\0') {
        const std::filesystem::path release_directory(release_value);

        // The regression test holds this continuation until it has observed
        // interest completion or client removal. Watch the containing
        // directory; the test atomically renames a fully written release file
        // into it, so the callback never observes a partially written gate.
        auto watcher = g_loop->resource<uvw::FsEventHandle>();
        watcher->on<uvw::FsEventEvent>(
            [continuation = std::move(continuation), release_directory](
                const uvw::FsEventEvent&, uvw::FsEventHandle& handle) mutable {
                std::error_code error;
                std::filesystem::path released_file;
                for(const auto& entry : std::filesystem::directory_iterator(
                        release_directory, error)) {
                    const std::string filename = entry.path().filename().string();
                    if(filename.rfind("release-", 0) != 0) {
                        continue;
                    }

                    std::ifstream release_file(entry.path());
                    std::string state;
                    if(release_file >> state && state == "release") {
                        released_file = entry.path();
                        break;
                    }
                }
                if(error) {
                    std::cerr << "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_WATCH_ERROR: "
                              << error.message() << std::endl;
                    return;
                }
                if(released_file.empty()) {
                    return;
                }

                handle.stop();
                handle.close();
                std::filesystem::remove(released_file, error);
                continuation();
                std::cout << "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RESUMED" << std::endl;
            });
        watcher->on<uvw::ErrorEvent>([](const uvw::ErrorEvent& event, uvw::FsEventHandle&) {
            std::cerr << "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_WATCH_ERROR: "
                      << event.what() << std::endl;
        });
        try {
            watcher->start(release_directory.string());
        } catch(const std::exception& error) {
            std::cerr << "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_WATCH_ERROR: "
                      << error.what() << std::endl;
            return;
        }
        std::cout << "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_GATE_READY" << std::endl;
        return;
    }
#endif
    continuation();
}

void IntegrationTestHooks::message_director_listening()
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    std::cout << "ASTRON_TEST_MESSAGE_DIRECTOR_LISTENING" << std::endl;
#endif
}

void IntegrationTestHooks::clientagent_ready()
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    std::cout << "ASTRON_TEST_CLIENTAGENT_READY" << std::endl;
#endif
}

void IntegrationTestHooks::channel_subscribed(channel_t channel)
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    std::cout << "ASTRON_TEST_CHANNEL_SUBSCRIBED:" << channel << std::endl;
#endif
}

void IntegrationTestHooks::configuration_ready()
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    std::cout << "ASTRON_TEST_CONFIGURATION_READY" << std::endl;
#endif
}
