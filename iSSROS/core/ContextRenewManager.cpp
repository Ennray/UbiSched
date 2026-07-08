//
// Created by zhengyanzhu on 2022/11/8.
//

#include "ContextRenewManager.h"
#include "../Utils/Utils.h"
#include <pthread.h>
#include <thread>
#include<sys/select.h>
#include<unistd.h>
#include<sys/types.h>
#include<sys/socket.h>
#include<arpa/inet.h>
#include<netinet/in.h>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <iostream>
//
//#define NUM_THREADS 5
//
//pthread_t tids[NUM_THREADS];
//void*(*funcAd[NUM_THREADS])(void *);
extern string obs0;
extern int listening_port;

void ContextRenewManager::init() {
//    funcAd[0] = getFog;
//    funcAd[1] = getRain;
//    funcAd[2] = getSnow;
//    funcAd[3] = getDust;
//    funcAd[4] = getLight;

}
void ContextRenewManager::run() {
    serverGetEnvData();
}

void ContextRenewManager::getFog() {

}

void ContextRenewManager::getRain() {

}

void ContextRenewManager::getLight() {

}

void ContextRenewManager::getSnow() {

}

void ContextRenewManager::getDust() {

}

//每秒取一次数据，封装一个environment类
void ContextRenewManager::serverGetEnvData() {
    auto util = Utils::GetInst();
    //仅接收，1个端口
    int port = listening_port;
    int sockfd;
    // 创建socket
    sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if(-1==sockfd){
        return ;
        puts("Failed to create socket");
    }

    // 设置地址与端口
    struct sockaddr_in addr;
    socklen_t addr_len = sizeof(addr);

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;       // Use IPV4
    addr.sin_port = htons(port);    //
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
//    addr.sin_addr.s_addr = inet_addr("192.168.137.3");

    // Time out
    struct timeval tv;
    tv.tv_sec  = 0;
    tv.tv_usec = 200000;  // 200 ms
    setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(struct timeval));

    // Bind 端口，用来接受之前设定的地址与端口发来的信息,作为接受一方必须bind端口，并且端口号与发送方一致
    if (bind(sockfd, (struct sockaddr*)&addr, addr_len) == -1){
        printf("Failed to bind socket on port %d\n", port);
        close(sockfd);
        return ;
    }

    char buffer[128];
    memset(buffer, 0, 128);

    int counter = 0;
    while(1){
        struct sockaddr_in src;
        socklen_t src_len = sizeof(src);
        memset(&src, 0, sizeof(src));

        // 阻塞住接受消息
        int sz = recvfrom(sockfd, buffer, 128, 0, (sockaddr*)&src, &src_len);
        if (sz > 0){
            buffer[sz] = 0;
            printf("Get Message %d: %s\n", counter++, buffer);
            vector<string> messages = util->split(buffer, "#");
            if (messages.size() >= 5) {
                WeatherBuilder weatherBuilder;
                Weather *weather = weatherBuilder
                    .fog(stof(messages[2]))
                    ->rain(stof(messages[3]))
                    ->dust(stof(messages[4]))
                    ->build();

                EnvironmentBuilder envBuilder;
                Environment *newEnv = envBuilder
                    .time(messages[0])
                    ->light(stof(messages[1]))
                    ->weather(*weather)
                    ->build();

                curEnv = newEnv;
                envReady = true;

                cout << "[ContextRenew] environment updated: "
                     << "time=" << messages[0]
                     << ", light=" << messages[1]
                     << ", fog=" << messages[2]
                     << ", rain=" << messages[3]
                     << ", dust=" << messages[4]
                     << endl;

                if (messages.size() >= 6) {
                    obs0 = messages[5];
                    cout << "[ContextRenew] obs updated: " << obs0 << endl;
                }
            } else {
                obs0 = buffer;
                cout << "[ContextRenew] obs updated: " << obs0 << endl;
            }
                // if(envReady){
                //     Weather weather = (Weather &) curEnv->getWeather();
                //     weather.setFog(stof(messages[2]));
                //     weather.setRain(stof(messages[3]));
                //     weather.setDust(stof(messages[4]));
                //     curEnv->setTime(messages[0]);
                //     curEnv->setLight(stof(messages[1]));
                //     curEnv->setWeather(weather);
                // }else{
                //     WeatherBuilder *builder = new WeatherBuilder;
                //     Weather *weather = builder->fog(stof(messages[2]))->rain(stof(messages[3]))->dust(stof(messages[4]))->build();
                //     delete builder;
                //     unique_lock<mutex> my_unique_lock(my_mutex);
                //     EnvironmentBuilder* builder1= new EnvironmentBuilder();
                //     curEnv = builder1->time(messages[0])->light(stof(messages[1]))->weather(*weather)->build();
                //     delete builder1;
                //     envReady = true;
                // }
                // cond.notify_one();
//                curEnv->show();
                startAssess = true;
            
        }

        //构造环境数据Environment

//        sleep(1);
    }

    close(sockfd);
}

// void ContextRenewManager::serverGetPosData() {
//     auto util = Utils::GetInst();
//     //仅接收，1个端口
//     int port = 8889;
//     int sockfd;
//     // 创建socket
//     sockfd = socket(AF_INET, SOCK_DGRAM, 0);
//     if(-1==sockfd){
//         return ;
//         puts("Failed to create socket");
//     }

//     // 设置地址与端口
//     struct sockaddr_in addr;
//     socklen_t addr_len = sizeof(addr);

//     memset(&addr, 0, sizeof(addr));
//     addr.sin_family = AF_INET;       // Use IPV4
//     addr.sin_port = htons(port);    //
//     addr.sin_addr.s_addr = htonl(INADDR_ANY);
// //    addr.sin_addr.s_addr = inet_addr("192.168.137.3");

//     // Time out
//     struct timeval tv;
//     tv.tv_sec  = 0;
//     tv.tv_usec = 200000;  // 200 ms
//     setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(struct timeval));

//     // Bind 端口，用来接受之前设定的地址与端口发来的信息,作为接受一方必须bind端口，并且端口号与发送方一致
//     if (bind(sockfd, (struct sockaddr*)&addr, addr_len) == -1){
//         printf("Failed to bind socket on port %d\n", port);
//         close(sockfd);
//         return ;
//     }

//     char buffer[256];
//     memset(buffer, 0, 256);

// //    std::unique_lock<mutex> sbguard1(my_mutex2);
// //    cond2.wait(sbguard1, [this] {
// //        if (!resourceCapTBReady) {
// //            return false;
// //        } else {
// //            return true;
// //        }
// //    });
// //    sbguard1.unlock();
//     while (!resourceCapTBReady){
// //        cout<<"11111111"<<endl;
// //        sleep(1);
//     }
// //    cout<<"11111111----------------"<<endl;
//     int counter = 0;
//     while(1){
//         struct sockaddr_in src;
//         socklen_t src_len = sizeof(src);
//         memset(&src, 0, sizeof(src));

//         // 阻塞住接受消息
//         int sz = recvfrom(sockfd, buffer, 256, 0, (sockaddr*)&src, &src_len);
//         if (sz > 0){
//             buffer[sz] = 0;
//             printf("Get 位置Message %d: %s\n", counter++, buffer);
//             vector<string> messages = util->split(buffer,"#");
//             if(messages.size()>1){
//                 cout<<"位置messages.size: "<<messages.size()<<endl;
// //                Weather *weather = (new WeatherBuilder())->fog(stof(messages[2]))->rain(stof(messages[3]))->dust(stof(messages[4]))->build();
//                 for (int i = 0; i < resourceCapTB.size(); ++i) {
//                     Capability* curCap = resourceCapTB[i];
//                     string uavName = curCap->getVehicleName();
// //                    Position* curP = NULL;
// //                    if(curCap->getPosition() == NULL){
// //                        curP = new Position(0.0,0.0,0.0,uavName);
// //                        resourceCapTB[i]->setPosition(curP);
// //                    }
//                     Position curP;
//                     char n = uavName[3];
//                     curP = curCap->getPosition();
//                     switch (n) {
//                         case '1':
//                             curP.setTime(messages[0]);
//                             curP.setN(stof(messages[1]));
//                             curP.setE(stof(messages[2]));
//                             curP.setD(stof(messages[3]));
//                             break;
//                         case '2':
//                             curP.setTime(messages[0]);
//                             curP.setN(stof(messages[4]));
//                             curP.setE(stof(messages[5]));
//                             curP.setD(stof(messages[6]));
//                             break;
//                         case '3':
//                             curP.setTime(messages[0]);
//                             curP.setN(stof(messages[7]));
//                             curP.setE(stof(messages[8]));
//                             curP.setD(stof(messages[9]));
//                             break;
//                         default:
//                             break;
//                     }
//                     curCap->setPosition(curP);
//                 }
// //                curEnv->show();
//                 startSelect = true;
//             }
//         }

//         //构造环境数据Environment


// //        sleep(1);
//     }

//     close(sockfd);
// }

