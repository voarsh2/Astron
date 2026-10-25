#include "clientagent/HistoricalObjectTracker.h"

#include <chrono>
#include <iostream>

namespace {

bool require(bool condition, const char *message)
{
    if(!condition) {
        std::cerr << message << std::endl;
    }
    return condition;
}

bool test_indefinite_retention()
{
    using namespace std::chrono;
    using Tracker = HistoricalObjectTracker;
    const Tracker::TimePoint now(milliseconds(1000));
    Tracker objects;
    objects.remember(1234, now);
    return require(objects.contains(1234, now + hours(24 * 365)),
                   "zero TTL did not retain historical objects indefinitely");
}

bool test_expiration_boundary()
{
    using namespace std::chrono;
    using Tracker = HistoricalObjectTracker;
    const Tracker::TimePoint now(milliseconds(1000));
    Tracker objects(milliseconds(100));
    objects.remember(1234, now);
    if(!require(objects.contains(1234, now + milliseconds(99)),
                "historical object expired before its TTL")) {
        return false;
    }
    return require(!objects.contains(1234, now + milliseconds(100)),
                   "historical object remained recognized at its TTL boundary");
}

bool test_reappearance_refreshes_expiration()
{
    using namespace std::chrono;
    using Tracker = HistoricalObjectTracker;
    const Tracker::TimePoint now(milliseconds(1000));
    Tracker objects(milliseconds(100));
    objects.remember(1234, now);
    objects.remember(1234, now + milliseconds(90));
    if(!require(objects.contains(1234, now + milliseconds(189)),
                "re-remembering did not refresh the historical object's TTL")) {
        return false;
    }
    return require(!objects.contains(1234, now + milliseconds(190)),
                   "refreshed historical object did not expire at its new TTL boundary");
}

bool test_large_ttl_saturates_at_clock_max()
{
    using namespace std::chrono;
    using Tracker = HistoricalObjectTracker;
    const Tracker::TimePoint now(milliseconds(1000));
    Tracker objects(milliseconds::max());
    objects.remember(1234, now);
    if(!require(objects.contains(1234, now + hours(24 * 365 * 100)),
                "large TTL overflowed before its expiration")) {
        return false;
    }
    return require(!objects.contains(1234, Tracker::TimePoint::max()),
                   "saturated historical object did not expire at the clock limit");
}

} // namespace

int main()
{
    return test_indefinite_retention() &&
           test_expiration_boundary() &&
           test_reappearance_refreshes_expiration() &&
           test_large_ttl_saturates_at_clock_max() ? 0 : 1;
}
