//
// Created by zhengyanzhu on 2022/11/9.
//

#ifndef IROS_CAPADAPTIVEMANAGER_H
#define IROS_CAPADAPTIVEMANAGER_H
#include <vector>
#include "../Cap/Capability.h"
#include "../Utils/Single_T.h"
#include "../env/Environment.h"
#include "../Cap/CapabilityNeed.h"
#include "../Cap/CapabilityAllocated.h"
#include "../Cap/CapabilityCanUse.h"

using namespace std;

class CapAdaptiveManager :public Single_T<CapAdaptiveManager> {
private:
    CapAdaptiveManager() = default;
    CapAdaptiveManager(const CapAdaptiveManager&) = delete;
    CapAdaptiveManager & operator=(const CapAdaptiveManager &) = delete;
    ~CapAdaptiveManager() = default;
    friend class SafeDeletor_T<CapAdaptiveManager>;
    friend class Single_T<CapAdaptiveManager>;
    bool select(
    const vector<vector<float>>& obs,
    const vector<float>& rnn_states,
    const vector<vector<vector<float>>>& available_actions,
    vector<float>& actions0,
    vector<float>& actions1
    );
public:
    void run();
//    vector<Capability*> assess(vector<Capability*> capabilities);
};

extern Environment* curEnv;
extern CapabilityNeed* capNeedTB;
extern vector<Capability* >resourceCapTB;
extern bool capNeedBuild;
extern vector<CapabilityCanUse> resourceCapCanUseTB;
extern CapabilityAllocated* resourceCapAllocatedTB;
//extern mutex my_mutex;
//extern std::condition_variable cond;
//extern volatile bool envReady;

#endif //IROS_CAPADAPTIVEMANAGER_H
