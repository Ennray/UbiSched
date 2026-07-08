//
// Created by zhengyanzhu on 2022/11/8.
//

#include <fstream>
#include <unistd.h>
#include "CapNeedManager.h"
#include "../Utils/Single_T.h"
#include "../CapInterface/CapInterfaceManager.h"
#include <future>
#include <mutex>
#include <shared_mutex>
#include <sys/stat.h>

using namespace std;
extern string obs0;
extern int weathernums;
//bool CapNeedManager::build = false;
//CapabilityNeed* CapNeedManager::CapNeedTB;
CapabilityNeed* CapNeedManager::getCapNeedTB(){
    if(build == false){
        cout<< "cap need 未构建"<<endl;
        return nullptr;
    }
    return CapNeedTB;
}
void CapNeedManager::buildCapNeedTB() {
    struct stat buf;
    lastMFTime = buf.st_mtime;
    cout <<"需求的最后修改时间： "<< lastMFTime << endl;

    if (CapNeedTB != nullptr) {
        delete CapNeedTB;
        CapNeedTB = nullptr;  
    }

    CapNeedTB = new CapabilityNeed();
    for(int i=weathernums;i<obs0.length();i++){
        CapNeedTB->add(obs0[i]-'0',10,0.8);
    }
    capNeedTB = CapNeedTB;
    build = true;
}
bool CapNeedManager::isBuild() {
    return build;
}
bool CapNeedManager::isModified() {
    return modified;
}

void CapNeedManager::run() {
    buildCapNeedTB();
    if(!isBuild()){
        cerr<<"capNeed build failed"<<endl;
        return;
    }
    cout <<"需求已经更新"<<endl;
    capNeedTB = getCapNeedTB();
}
