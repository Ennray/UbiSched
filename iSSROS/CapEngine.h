//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_CAPENGINE_H
#define IROS_CAPENGINE_H

#include "./Utils/Single_T.h"
#include "Cap/CapabilityNeed.h"
#include "Cap/Capability.h"
#include <vector>
#include "env/Environment.h"
#include "Cap/CapabilityAllocated.h"
#include <mutex>
#include <shared_mutex>
#include <condition_variable>

using namespace std;

class CapEngine : public Single_T<CapEngine>{
private:
    CapEngine() = default;
    CapEngine(const CapEngine&) = delete;
    CapEngine & operator=(const CapEngine &) = delete;
    ~CapEngine() = default;
    friend class SafeDeletor_T<CapEngine>;
    friend class Single_T<CapEngine>;
    shared_timed_mutex mutex_;
public:
    void init();
    void run();
};
extern CapabilityNeed* capNeedTB;
extern vector<Capability* >resourceCapTB;
extern CapabilityAllocated* resourceCapAllocatedTB;
extern bool capNeedBuild;
extern Environment* curEnv;
extern std::condition_variable cond;
extern mutex my_mutex;
extern volatile bool envReady;

extern mutex my_mutex2;
extern volatile bool resourceCapTBReady;
extern std::condition_variable cond2;

extern bool startAssess;
extern bool startSelect;

#endif //IROS_CAPENGINE_H
