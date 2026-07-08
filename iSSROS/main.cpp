#include <iostream>
#include <thread>
#include "Cap/Parameter.h"
#include "Cap/Capability.h"
#include "CapInterface/CapInterfaceManager.h"
#include "CapEngine.h"
#include "core/CapNeedManager.h"
#include "core/ContextRenewManager.h"
#include "Utils/Utils.h"

#include "core/CapDispatchManager.h"

extern int listening_port;
extern string Uavname;
extern int UAVid;
static const int threadCount=3;
using namespace std;
int main(int argc,char *argv[]) {
    if (argc < 3) {
        std::cerr << "example: " << argv[0] << " port UAVid(begin from 1)" << std::endl;
        return 1;
    }
    listening_port = stoi(argv[1]);
    UAVid = stoi(argv[2]);

    // Print initial configuration
    string dest_ip = Utils::GetInst()->getConf("config.ini", "DEST_IP_ADDRESS");
    if (dest_ip.empty()) dest_ip = Utils::GetInst()->getConf("../config.ini", "DEST_IP_ADDRESS");
    if (dest_ip.empty()) dest_ip = Utils::GetInst()->getConf("../../config.ini", "DEST_IP_ADDRESS");
    if (dest_ip.empty()) dest_ip = "192.168.137.1"; // Fallback

    int target_port = CapDispatchManager::DEST_PORT - UAVid + 1;
    cout << "========================================" << endl;
    cout << "IROS Starting..." << endl;
    cout << "Listening Port: " << listening_port << endl;
    cout << "UAV ID: " << UAVid << endl;
    cout << "Target Dispatch IP: " << dest_ip << endl;
    cout << "Target Dispatch Port: " << target_port << endl;
    cout << "========================================" << endl;

    thread t[threadCount];
    auto CRM = ContextRenewManager::GetInst();
    auto Engine = CapEngine::GetInst();
    t[0] = thread(&ContextRenewManager::serverGetEnvData,CRM);
    t[1] = thread(&CapEngine::run,Engine);
    // t[2] = thread(&ContextRenewManager::serverGetPosData,CRM);


    for (int i = 0; i < threadCount; ++i) {
        t[i].join();
    }
//    pause();
    return 0;
}
