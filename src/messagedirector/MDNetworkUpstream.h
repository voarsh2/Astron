#pragma once
#include "MessageDirector.h"
#include "net/NetworkClient.h"
#include "net/NetworkConnector.h"

// All MDUpstreams must be thread-safe. Protect the staged queue and connection
// transition because routing threads can send while the upstream connects.
class MDNetworkUpstream : public NetworkHandler, public MDUpstream
{
  public:
    MDNetworkUpstream(MessageDirector *md, uint64_t max_write_buffer_bytes);

    void connect(const std::string &address);
    void on_connect(const std::shared_ptr<uvw::TcpHandle> &socket);
    void on_connect_error(const uvw::ErrorEvent& evt);

    // Queueing interfaces for datagrams pending being sent upstream.
    void send_datagram(DatagramHandle dg);

    // Interfaces that MDUpstream needs us to implement:
    virtual void subscribe_channel(channel_t c);
    virtual void unsubscribe_channel(channel_t c);
    virtual void subscribe_range(channel_t lo, channel_t hi);
    virtual void unsubscribe_range(channel_t lo, channel_t hi);
    virtual void handle_datagram(DatagramHandle dg);

    // Interfaces that NetworkClient needs us to implement:
    virtual void initialize()
    {
        // Stub method for NetworkClient.
    }

    virtual void receive_datagram(DatagramHandle dg);
    virtual void receive_disconnect(const uvw::ErrorEvent &evt);

  private:
    MessageDirector *m_message_director;
    std::shared_ptr<NetworkClient> m_client;
    std::shared_ptr<NetworkConnector> m_connector;
    std::mutex m_messages_lock;
    std::queue<DatagramHandle> m_messages;
    uint64_t m_max_queue_size;
    uint64_t m_pending_queue_size = 0;
    bool m_initialized = false;
};
