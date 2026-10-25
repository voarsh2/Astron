#pragma once

#include "core/types.h"

#include <chrono>
#include <map>
#include <unordered_map>
#include <unordered_set>

// Remembers object IDs that were once visible to a client. A zero TTL keeps
// the historical behavior indefinitely; a positive TTL expires old entries.
class HistoricalObjectTracker
{
  public:
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;

    explicit HistoricalObjectTracker(std::chrono::milliseconds ttl =
                                         std::chrono::milliseconds::zero()) :
        m_ttl(ttl)
    {
    }

    void remember(doid_t do_id, TimePoint now = Clock::now())
    {
        if(m_ttl <= std::chrono::milliseconds::zero()) {
            m_indefinite_objects.insert(do_id);
            return;
        }

        expire(now);

        auto previous = m_expiration_by_object.find(do_id);
        if(previous != m_expiration_by_object.end()) {
            m_expirations.erase(previous->second);
            m_expiration_by_object.erase(previous);
        }

        const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
            TimePoint::max() - now);
        const TimePoint expires_at = m_ttl >= remaining ? TimePoint::max() : now + m_ttl;
        auto expiration = m_expirations.emplace(expires_at, do_id);
        m_expiration_by_object.emplace(do_id, expiration);
    }

    bool contains(doid_t do_id, TimePoint now = Clock::now())
    {
        if(m_ttl <= std::chrono::milliseconds::zero()) {
            return m_indefinite_objects.find(do_id) != m_indefinite_objects.end();
        }

        expire(now);
        return m_expiration_by_object.find(do_id) != m_expiration_by_object.end();
    }

  private:
    using ExpirationMap = std::multimap<TimePoint, doid_t>;

    void expire(TimePoint now)
    {
        while(!m_expirations.empty() && m_expirations.begin()->first <= now) {
            doid_t do_id = m_expirations.begin()->second;
            m_expirations.erase(m_expirations.begin());
            m_expiration_by_object.erase(do_id);
        }
    }

    std::chrono::milliseconds m_ttl;
    std::unordered_set<doid_t> m_indefinite_objects;
    ExpirationMap m_expirations;
    std::unordered_map<doid_t, ExpirationMap::iterator> m_expiration_by_object;
};
