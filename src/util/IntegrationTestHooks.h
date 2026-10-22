#pragma once

#include <functional>

namespace IntegrationTestHooks
{
void run_after_interest_timeout_setup_delay(std::function<void()> continuation);
}
