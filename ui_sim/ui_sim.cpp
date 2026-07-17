#include <iostream>
#include <string>

#include <zmq.hpp>
#include <nlohmann/json.hpp>
#include <queue>
#include <mutex>
#include <atomic>
#include <thread>

// -----------------------------------------------------------------------------
// Thread-safe queue
// -----------------------------------------------------------------------------
template<typename T>
class ThreadSafeQueue {
public:
    void push(T value)
    {
        std::lock_guard lock(mutex_);
        queue_.push(std::move(value));
    }

    bool try_pop(T& value)
    {
        std::lock_guard lock(mutex_);

        if(queue_.empty())
            return false;

        value = std::move(queue_.front());
        queue_.pop();
        return true;
    }

private:
    std::queue<T> queue_;
    std::mutex mutex_;
};

// -----------------------------------------------------------------------------
// Messages sent from ZMQ thread to UI thread
// -----------------------------------------------------------------------------
struct UiMessage
{
    int loop;
    double pos;
};

static ThreadSafeQueue<UiMessage> g_queue;
static std::atomic_bool g_running{true};

// -----------------------------------------------------------------------------
// ZMQ receiver thread
// -----------------------------------------------------------------------------

void zmq_receiver()
{
    try {
        zmq::context_t context(1);
        zmq::socket_t subscriber(context, zmq::socket_type::sub);

        // Connect to publisher
        subscriber.connect("tcp://localhost:9956");

        // Subscribe to all messages (empty filter)
        subscriber.set(zmq::sockopt::subscribe, "");


        while (g_running) {

            zmq::message_t msg;

            auto result = subscriber.recv(
                msg,
                zmq::recv_flags::none);

            if (!result) {
                continue;
            }

            // Convert to string
            std::string msg_str(static_cast<char*>(msg.data()), msg.size());

            try {
                // Parse JSON
                nlohmann::json j = nlohmann::json::parse(msg_str);
                // std::cout << "type: " << j.type_name() << '\n';
                // std::cout << "dump: " << j.dump() << '\n';
                // std::cout << j << std::endl;
                // Use JSON
                UiMessage d;
                if (j.contains("loop"))
                    d.loop = j["loop"].get<int>();

                if (j.contains("data"))
                    d.pos = j["data"].get<double>();

                g_queue.push({std::move(d)});

            } catch (const nlohmann::json::parse_error& e) {
                std::cerr << "JSON parse error: " << e.what() << std::endl;
            }
        }
    }
    catch (const std::exception& e) {
        printf("ZMQ error: %s\n", e.what());
    }
}

void lvgl_simu()
{
    UiMessage msg;

    // Process all pending messages
    while (g_queue.try_pop(msg)) {
        std::cout << "loop: " << msg.loop << " pos: " << msg.pos << std::endl;
    }
    std::this_thread::sleep_for(
        std::chrono::milliseconds(5));
}

int main() {

    // LVGL initialization
    // lv_init();

    // --------------------------------------------------
    // Initialize display driver here
    // Initialize input driver here
    // --------------------------------------------------

    // create_ui();

    std::thread receiver_thread(zmq_receiver);

    // create lv_timer to pop from the queue!!!

    // LVGL loop
    while (true) {

        // lv_timer_handler();
        lvgl_simu();
        std::this_thread::sleep_for(
            std::chrono::milliseconds(5));
    }

    g_running = false;

    receiver_thread.join();

    return 0;
}