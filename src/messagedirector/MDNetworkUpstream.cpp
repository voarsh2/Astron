#include "MDNetworkUpstream.h"
#include "MessageDirector.h"
#include "net/NetworkConnector.h"
#include "core/global.h"
#include "core/msgtypes.h"
#include "util/IntegrationTestHooks.h"
#include "util/TaskQueue.h"

#include <thread>
#include <utility>

MDNetworkUpstream::MDNetworkUpstream(MessageDirector *md, uint64_t max_write_buffer_bytes) :
    m_message_director(md), m_client(std::make_shared<NetworkClient>(this)),
    m_connector(std::make_shared<NetworkConnector>(g_loop)),
    m_max_queue_size(max_write_buffer_bytes)
{
    m_client->set_write_buffer(max_write_buffer_bytes);
}

void MDNetworkUpstream::connect(const std::string &address)
{
    ConnectCallback callback = std::bind(&MDNetworkUpstream::on_connect, this, std::placeholders::_1);
    ConnectErrorCallback err_callback = std::bind(&MDNetworkUpstream::on_connect_error, this, std::placeholders::_1);

    m_connector->connect(address, 7199, callback, err_callback);
}

void MDNetworkUpstream::on_connect(const std::shared_ptr<uvw::TcpHandle> &socket)
{
    if(socket == nullptr) {
        m_message_director->receive_disconnect(uvw::ErrorEvent{(int)UV_EADDRNOTAVAIL});
        exit(1);
    }

    IntegrationTestHooks::run_before_upstream_ready([this, socket]() {
        m_client->initialize(socket);

        // Drain staged datagrams and publish initialized under the same lock
        // used by send_datagram. Each sender either joins this drain or sees
        // the connected client after it; no datagram can be stranded between
        // the two paths.
        auto lock = std::make_shared<std::unique_lock<std::mutex>>(m_messages_lock);
        IntegrationTestHooks::run_before_upstream_queue_drain([this, lock]() {
            while(!m_messages.empty()) {
                DatagramHandle dg = m_messages.front();
                m_messages.pop();
                m_pending_queue_size -= static_cast<uint64_t>(dg->size());
                m_client->send_datagram(dg);
            }
            m_initialized = true;
            lock->unlock();

            m_connector->destroy();
            m_connector = nullptr;
        });
    });
}

void MDNetworkUpstream::send_datagram(DatagramHandle dg)
{
    IntegrationTestHooks::upstream_send_attempted(m_messages_lock);
    bool send_now = false;
    bool queue_limit_exceeded = false;
    {
        std::lock_guard<std::mutex> lock(m_messages_lock);
        if(m_initialized) {
            send_now = true;
        } else {
            const uint64_t datagram_size = static_cast<uint64_t>(dg->size());
            if(m_max_queue_size != 0 &&
               (datagram_size > m_max_queue_size ||
                m_pending_queue_size > m_max_queue_size - datagram_size)) {
                queue_limit_exceeded = true;
            } else {
                m_messages.push(dg);
                m_pending_queue_size += datagram_size;
            }
        }
    }

    if(queue_limit_exceeded) {
        IntegrationTestHooks::write_buffer_overflow();
        MessageDirector *message_director = m_message_director;
        auto disconnect = [message_director]() {
            message_director->receive_disconnect(uvw::ErrorEvent{(int)UV_ENOBUFS});
        };
        if(std::this_thread::get_id() == g_main_thread_id) {
            disconnect();
        } else {
            TaskQueue::singleton.enqueue_task(std::move(disconnect));
        }
    } else if(send_now) {
        m_client->send_datagram(dg);
    }
}

void MDNetworkUpstream::on_connect_error(const uvw::ErrorEvent& evt)
{
    m_message_director->receive_disconnect(evt);
}

void MDNetworkUpstream::subscribe_channel(channel_t c)
{
    DatagramPtr dg = Datagram::create(CONTROL_ADD_CHANNEL);
    dg->add_channel(c);
    send_datagram(dg);
}

void MDNetworkUpstream::unsubscribe_channel(channel_t c)
{
    DatagramPtr dg = Datagram::create(CONTROL_REMOVE_CHANNEL);
    dg->add_channel(c);
    send_datagram(dg);
}

void MDNetworkUpstream::subscribe_range(channel_t lo, channel_t hi)
{
    DatagramPtr dg = Datagram::create(CONTROL_ADD_RANGE);
    dg->add_channel(lo);
    dg->add_channel(hi);
    send_datagram(dg);
}

void MDNetworkUpstream::unsubscribe_range(channel_t lo, channel_t hi)
{
    DatagramPtr dg = Datagram::create(CONTROL_REMOVE_RANGE);
    dg->add_channel(lo);
    dg->add_channel(hi);
    send_datagram(dg);
}

void MDNetworkUpstream::handle_datagram(DatagramHandle dg)
{
    send_datagram(dg);
}

void MDNetworkUpstream::receive_datagram(DatagramHandle dg)
{
    m_message_director->receive_datagram(dg);
}

void MDNetworkUpstream::receive_disconnect(const uvw::ErrorEvent &evt)
{
    m_message_director->receive_disconnect(evt);
}
