#pragma once

#include <functional>

#include "core/types.h"

namespace IntegrationTestHooks
{
void run_after_interest_timeout_setup(std::function<void()> continuation);
void message_director_listening();
void clientagent_ready();
void channel_subscribed(channel_t channel);
void configuration_ready();
}
