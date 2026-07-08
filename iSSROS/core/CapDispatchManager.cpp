//
// Created by zhengyanzhu on 2022/11/9.
//

#include "CapDispatchManager.h"
#include "../Resource/Resource.h"
#include <iostream>
#include <vector>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <cstring>
#include "../CapInterface/CapInterfaceManager.h"
#include <string>


#include "../Utils/Utils.h"

using namespace std;

extern int UAVid;

void CapDispatchManager::run(CapabilityAllocated *capAllocated) {
    string dest_ip = Utils::GetInst()->getConf("config.ini", "DEST_IP_ADDRESS");
    if (dest_ip.empty()) {
        dest_ip = Utils::GetInst()->getConf("../config.ini", "DEST_IP_ADDRESS");
    }
    if (dest_ip.empty()) {
        dest_ip = Utils::GetInst()->getConf("../../config.ini", "DEST_IP_ADDRESS");
    }
    if (dest_ip.empty()) {
        dest_ip = "192.168.137.1"; // Default fallback
    }
    
    if(capAllocated==NULL || capAllocated->isEmpty()){
        cout<<"capAllocated 空"<<endl;
        return;
    }
    vector<Resource*> resources;
    map<int,int> capAlo = capAllocated->getId2Id();
    for (map<int,int>::iterator iter = capAlo.begin(); iter != capAlo.end(); ++iter) {
        cout << iter->first<<" "<<iter->second<<" "<<endl;
        if(false){
            cerr<<"能力需求未匹配完成"<<endl;
            return;
        } else{
            Resource* tmp = new Resource();
            tmp->setImageType(iter->second);
            tmp->setVehicleName("UAV"+to_string(UAVid));
            tmp->setTaskid(iter->first);
            tmp->setResourceName(std::to_string(iter->second));
            resources.push_back(tmp);
            //result
        }
    }
    //发送指令，让airsim只截resources里的图


    /* socket文件描述符 */
    int sock_fd;

    /* 建立udp socket */
    sock_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if(sock_fd < 0)
    {
        perror("socket");
        exit(1);
    }

    /* 设置address */
    struct sockaddr_in addr_serv;
    int len;
    memset(&addr_serv, 0, sizeof(addr_serv));
    addr_serv.sin_family = AF_INET;
    addr_serv.sin_addr.s_addr = inet_addr(dest_ip.c_str());
    int target_port = DEST_PORT - UAVid + 1;
    cout << "Dispatching to IP: " << dest_ip << ", Port: " << target_port << endl;
    addr_serv.sin_port = htons(target_port);
    len = sizeof(addr_serv);

    int messageCount = resources.size();
    string mes = "";
    for (int i = 0; i < messageCount; ++i) {
        mes += to_string(resources[i]->getTaskid())+'#'+to_string(resources[i]->getImageType())+"#"+resources[i]->getVehicleName();
        if(i != messageCount-1){
            mes += " ";
        }
//        send_buf = (char *)(to_string(resources[i]->getImageType())+resources[i]->getVehicleName()).c_str();
        cout<<"mes: "<<mes<<endl;
    }
    char * send_buf =  (char *)(mes.c_str());
    int send_num;
    printf("client send: %s\n", send_buf);

    send_num = sendto(sock_fd, send_buf, strlen(send_buf), 0, (struct sockaddr *)&addr_serv, len);

    if(send_num < 0)
    {
        perror("sendto error:");
        exit(1);
    }
}
