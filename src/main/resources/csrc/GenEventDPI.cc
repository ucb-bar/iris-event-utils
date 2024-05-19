#include <svdpi.h>
#include <vector>
#include <fstream> 
#include <iostream> 

class EventLog {
public:
    void add_event(char* event_name,
                    long long int id,
                    long long int parent,
                    long long int cycle,
                    long long int data) {
        event_entry new_event = {event_name, id, parent, cycle, data};
        event_vector.push_back(new_event);
    }
    ~EventLog() {
        std::ofstream file("GenEventLog.txt");
        if (file.is_open()) {
            for (const auto& event : event_vector) {
                file
                << event.event_name  << " "
                << event.id << " "
                << event.parent << " "
                << event.cycle << " "
                << event.data << " \n"
                ;
            }
            file.close();
            std::cout << "Events written to file.\n";
        } else {
            std::cerr << "Event log FAILED.\n";
        }
    }
private:
    struct event_entry {
        char * event_name;
        int64_t id;
        int64_t parent;
        int64_t cycle;
        int64_t data;
    };

    std::vector<event_entry> event_vector;
};

EventLog event_log;

extern "C" void gen_event_export(char* event_name,
                                 long long int id,
                                 long long int parent,
                                 long long int cycle,
                                 long long int data) {
    event_log.add_event(event_name, id, parent, cycle, data);
}

