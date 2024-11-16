#include <svdpi.h>
#include <vector>
#include <fstream> 
#include <iostream> 
#include <string>
#include <zlib.h>

class EventLog {
public:   
    void add_event(std::string event_name,
                    long long int id,
                    long long int parent,
                    long long int cycle,
                    long long int data) {
        event_entry new_event{event_name, id, parent, cycle, data};
        // std::cout << event_name << "\n";
        // std::cout << "hi there!" << "\n";
        event_vector.push_back(new_event);
    }
    EventLog() { 
        std::cout << "EventLog constructor called\n";
    }
    ~EventLog() {
        std::cout << "EventLog destructor called\n";
        std::ofstream file("GenEventLog.txt");
        if (file.is_open()) {
            for (const event_entry& event : event_vector) {
                // event.writeToFile(file);
                file
                << event.event_name  << " "
                << event.id << " "
                << event.parent << " "
                << event.cycle << " "
                << event.data << " \n"
                ;
            }
            file.close();
            std::cout << "Events successfully written to file.\n";
        } else {
            std::cerr << "Event log FAILED.\n";
        }
    }
private:
    struct event_entry {
        std::string event_name;
        int64_t id;
        int64_t parent;
        int64_t cycle;
        int64_t data;

        // void writeToFile(std::ofstream& file) const {
        //     // Write the string length followed by the string data
        //     size_t length = event_name.size();
        //     file.write(reinterpret_cast<const char*>(&length), sizeof(length));
        //     file.write(event_name.data(), length);
        //     // Write the integer
        //     file.write(reinterpret_cast<const char*>(&id), sizeof(id));
        //     file.write(reinterpret_cast<const char*>(&parent), sizeof(parent));
        //     file.write(reinterpret_cast<const char*>(&cycle), sizeof(cycle));
        //     file.write(reinterpret_cast<const char*>(&data), sizeof(data));
        // }
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

