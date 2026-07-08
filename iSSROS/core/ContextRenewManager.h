//
// Created by zhengyanzhu on 2022/11/8.
//

#ifndef IROS_CONTEXTRENEWMANAGER_H
#define IROS_CONTEXTRENEWMANAGER_H
#include "../Utils/Single_T.h"
#include "../env/Environment.h"
#include "../Cap/Capability.h"
#include <condition_variable>
#include <vector>

//:public Single_T<ContextRenewManager>
class ContextRenewManager :public Single_T<ContextRenewManager>{
private:
    ContextRenewManager() = default;
    ContextRenewManager(const ContextRenewManager&) = delete;
    ContextRenewManager & operator=(const ContextRenewManager &) = delete;
    ~ContextRenewManager() = default;
    friend class SafeDeletor_T<ContextRenewManager>;
    friend class Single_T<ContextRenewManager>;

public:
    void run();
    void init();
    void getFog();
    void getRain();
    void getLight();
    void getSnow();
    void getDust();
    void serverGetEnvData();
    void serverGetPosData();
};

extern Environment* curEnv;
extern mutex my_mutex;
extern std::condition_variable cond;
extern volatile bool envReady;
extern vector<Capability* >resourceCapTB;

extern mutex my_mutex2;
extern std::condition_variable cond2;
extern volatile bool resourceCapTBReady;


extern bool startAssess;
extern bool startSelect;
#endif //IROS_CONTEXTRENEWMANAGER_H
