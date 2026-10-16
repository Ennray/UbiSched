// Build manually: g++ -std=c++11 -I iSSROS/core scripts/stage12_cpp_probe.cpp -o /tmp/ubisched_cpp_probe
#include "UbiSchedBridgeClient.h"
#include <iostream>
int main(int argc, char** argv) {
    int task = -1, sensor = -1;
    const char *obs = argc > 1 ? argv[1] : "1110";
    UbiSchedBridgeClient::Result r = UbiSchedBridgeClient::request(1, obs, task, sensor);
    std::cout << static_cast<int>(r) << "|" << task << "|" << sensor << '\n';
    return 0;
}
