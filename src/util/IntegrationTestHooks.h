#pragma once

#include <functional>
#include <mutex>

#include "core/types.h"

namespace IntegrationTestHooks
{
void run_after_interest_timeout_setup(std::function<void()> continuation);
void message_director_listening();
void clientagent_ready();
void channel_subscribed(channel_t channel);
void configuration_ready();
void run_before_upstream_ready(std::function<void()> continuation);
void run_before_upstream_queue_drain(std::function<void()> continuation);
void run_before_network_write_completion(std::function<void()> continuation);
void upstream_send_attempted(std::mutex &lock);
void write_buffer_overflow();
}
