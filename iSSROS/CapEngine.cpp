//
// Created by zhengyanzhu on 2022/11/7.
//

#include "CapEngine.h"
#include "CapInterface/CapInterfaceManager.h"
#include "core/CapNeedManager.h"
#include "core/CapAdaptiveManager.h"
#include "core/CapDispatchManager.h"
#include <thread>
#include <unistd.h>

extern bool startAssess;

void CapEngine::init() {
}

void CapEngine::run() {
    auto CNM = CapNeedManager::GetInst();
    auto CIM = CapInterfaceManager::GetInst();
    auto CAM = CapAdaptiveManager::GetInst();
    auto CDM = CapDispatchManager::GetInst();
    CNM->run();//构建能力需求
    cout<<"初始能力需求如下："<<endl;
    capNeedTB->show();
    
    resourceCapTB = CIM->getCapabilityFromTxt("./sensors.txt");
    resourceCapTBReady = true;
    cout << "感知资源属性：" << endl;
    for (int i = 0; i < resourceCapTB.size(); ++i) {
        resourceCapTB[i]->show();
    }
    while(1){
        // startAssess = true;
        while(!(startAssess)){
        // while(!(startAssess && startSelect)){//收到天气的变化测开始评估
            cout<<"wait to Assess & Select,sleep(1)"<<' '<<startAssess<<endl;
            sleep(1);
        }
        CNM->run();
        CAM->run();
        cout<<"Adaptive 调用"<<endl;
//            }
//        }
        //dispatch调度给airsim发结果
        CDM->run(resourceCapAllocatedTB);
        startAssess = false;
        startSelect = false;
        cout<<"Dispatch 调用"<<endl;

        CNM->run();//构建能力需求
        if(CNM->isBuild()){
            if(CNM->isModified()){
                cout<<"当前能力需求如下："<<endl;
                capNeedTB->show();
                resourceCapTB = CIM->getCapabilityFromTxt("./sensors.txt");
                resourceCapTBReady = true;
                cout << "当前相关资源能力如下：" << endl;
                for (int i = 0; i < resourceCapTB.size(); ++i) {
                    resourceCapTB[i]->show();
                }
            } else{
//                sleep(5);
            }
        }
//        sleep(5);
    }
}
