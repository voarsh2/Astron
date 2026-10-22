#include "IntegrationTestHooks.h"
#include "core/global.h"

#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
#include <cstdlib>
#include <fstream>
#include <string>
#endif

#include <utility>

void IntegrationTestHooks::run_after_interest_timeout_setup_delay(
    std::function<void()> continuation)
{
#ifdef ASTRON_ENABLE_INTEGRATION_TEST_HOOKS
    const char* value = std::getenv("ASTRON_TEST_DELAY_INTEREST_TIMEOUT_SETUP_MS");
    if(value != nullptr) {
        char* end = nullptr;
        const unsigned long delay_ms = std::strtoul(value, &end, 10);
        if(end != value && *end == '\0' && delay_ms > 0 && delay_ms <= 10000) {
            const char* release_value = std::getenv(
                "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RELEASE_FILE");
            const std::string release_path = release_value == nullptr ? "" : release_value;
            const char* marker_value = std::getenv(
                "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RESUMED_FILE");
            const std::string marker_path = marker_value == nullptr ? "" : marker_value;

            // Keep polling the event loop until the test releases this
            // continuation. This makes completion/disconnect ordering
            // deterministic instead of relying on a delay beating the runner.
            auto timer = g_loop->resource<uvw::TimerHandle>();
            timer->on<uvw::TimerEvent>(
                [continuation = std::move(continuation), release_path, marker_path](
                    const uvw::TimerEvent&, uvw::TimerHandle& handle) mutable {
                    if(!release_path.empty() && !std::ifstream(release_path).good()) {
                        return;
                    }

                    handle.stop();
                    handle.close();
                    continuation();

                    if(!marker_path.empty()) {
                        std::ofstream marker(marker_path, std::ios::app);
                        marker << "resumed\n";
                    }
                });
            timer->start(
                uvw::TimerHandle::Time{delay_ms},
                uvw::TimerHandle::Time{release_path.empty() ? 0 : 10});
            return;
        }
    }
#endif
    continuation();
}
