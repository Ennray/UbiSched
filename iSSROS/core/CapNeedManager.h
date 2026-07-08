//
// Created by zhengyanzhu on 2022/11/8.
//

#ifndef IROS_CAPNEEDMANAGER_H
#define IROS_CAPNEEDMANAGER_H

#include "../Utils/Single_T.h"
#include "../Cap/CapabilityNeed.h"
#include "../Cap/Capability.h"
#include <vector>

class CapNeedManager : public Single_T<CapNeedManager>{
private:
    CapNeedManager() = default;
    CapNeedManager(const CapNeedManager&) = delete;
    CapNeedManager & operator=(const CapNeedManager &) = delete;
    ~CapNeedManager() = default;
    friend class SafeDeletor_T<CapNeedManager>;
    friend class Single_T<CapNeedManager>;

    bool build;
    CapabilityNeed* CapNeedTB;
    long lastMFTime;
    bool modified;
    shared_timed_mutex mutex_;
public:
    CapabilityNeed* getCapNeedTB();
    void buildCapNeedTB();
    bool isBuild();
    bool isModified();
    void run();
};
extern CapabilityNeed* capNeedTB;
extern vector<Capability* >resourceCapTB;
extern bool capNeedBuild;
extern volatile bool resourceCapTBReady;

#endif //IROS_CAPNEEDMANAGER_H
