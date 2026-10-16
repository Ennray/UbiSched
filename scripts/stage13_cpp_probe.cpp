#include "UbiSchedStructuredClient.h"
#include <cstdlib>
#include <iostream>
int main(int argc, char** argv) {
    const char* path = argc > 1 ? argv[1] : "configs/ubisched/structured_snapshot_example.json";
    const char* obs = argc > 2 ? argv[2] : "1111111";
    int task=-1,sensor=-1;
    UbiSchedBridgeClient::Result result = UbiSchedStructuredClient::request(1, obs, path, task, sensor);
    std::cout << int(result) << "|" << task << "|" << sensor << "\n";
    return 0;
}
