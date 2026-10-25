#include "IntegrationTestHooks.h"
#include "core/global.h"

#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <unordered_set>
#endif

#include <utility>

namespace {

#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
void run_after_release_gate(const char *environment_variable,
                            const char *ready_marker,
                            const char *resumed_marker,
                            std::function<void()> continuation,
                            bool once,
                            bool require_arm)
{
    const char* release_value = std::getenv(environment_variable);
    if(release_value == nullptr || *release_value == '\0') {
        continuation();
        return;
    }

    const std::filesystem::path release_directory(release_value);
    std::error_code error;
    if(require_arm && !std::filesystem::exists(release_directory / "arm", error)) {
        continuation();
        return;
    }

    static std::unordered_set<std::string> used_gates;
    if(once && !used_gates.insert(environment_variable).second) {
        continuation();
        return;
    }

    auto resume = std::make_shared<std::function<void()>>(std::move(continuation));
    auto watcher = g_loop->resource<uvw::FsEventHandle>();
    watcher->on<uvw::FsEventEvent>(
        [resume, release_directory,
         resumed_marker](const uvw::FsEventEvent&, uvw::FsEventHandle& handle) mutable {
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
                std::cerr << "ASTRON_TEST_GATE_WATCH_ERROR: "
                          << error.message() << std::endl;
                return;
            }
            if(released_file.empty()) {
                return;
            }

            handle.stop();
            handle.close();
            std::filesystem::remove(released_file, error);
            auto continuation = std::move(*resume);
            *resume = {};
            continuation();
            std::cout << resumed_marker << std::endl;
        });
    watcher->on<uvw::ErrorEvent>([](const uvw::ErrorEvent& event, uvw::FsEventHandle&) {
        std::cerr << "ASTRON_TEST_GATE_WATCH_ERROR: " << event.what() << std::endl;
    });
    try {
        watcher->start(release_directory.string());
    } catch(const std::exception& error) {
        std::cerr << "ASTRON_TEST_GATE_WATCH_ERROR: " << error.what() << std::endl;
        watcher->close();
        auto callback = std::move(*resume);
        *resume = {};
        callback();
        return;
    }
    std::cout << ready_marker << std::endl;
}
#endif

} // namespace

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

void IntegrationTestHooks::run_before_upstream_ready(std::function<void()> continuation)
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    run_after_release_gate(
        "ASTRON_TEST_UPSTREAM_READY_RELEASE_DIRECTORY",
        "ASTRON_TEST_UPSTREAM_READY_GATE_READY",
        "ASTRON_TEST_UPSTREAM_READY_GATE_RESUMED",
        std::move(continuation), true, false);
#else
    continuation();
#endif
}

void IntegrationTestHooks::run_before_upstream_queue_drain(
    std::function<void()> continuation)
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    run_after_release_gate(
        "ASTRON_TEST_UPSTREAM_DRAIN_RELEASE_DIRECTORY",
        "ASTRON_TEST_UPSTREAM_DRAIN_GATE_READY",
        "ASTRON_TEST_UPSTREAM_DRAIN_GATE_RESUMED",
        std::move(continuation), true, false);
#else
    continuation();
#endif
}

void IntegrationTestHooks::run_before_network_write_completion(
    std::function<void()> continuation)
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    run_after_release_gate(
        "ASTRON_TEST_NETWORK_WRITE_RELEASE_DIRECTORY",
        "ASTRON_TEST_NETWORK_WRITE_GATE_READY",
        "ASTRON_TEST_NETWORK_WRITE_GATE_RESUMED",
        std::move(continuation), true, true);
#else
    continuation();
#endif
}

void IntegrationTestHooks::upstream_send_attempted(std::mutex &lock)
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    if(!lock.try_lock()) {
        std::cout << "ASTRON_TEST_UPSTREAM_SEND_LOCK_BLOCKED" << std::endl;
        return;
    }
    lock.unlock();
#else
    (void)lock;
#endif
}

void IntegrationTestHooks::write_buffer_overflow()
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    std::cout << "ASTRON_TEST_WRITE_BUFFER_OVERFLOW" << std::endl;
#endif
}
