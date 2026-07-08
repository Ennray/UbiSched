//
// Created by zhengyanzhu on 2022/11/9.
//

#ifndef IROS_CAPDISPATCHMANAGER_H
#define IROS_CAPDISPATCHMANAGER_H
#include "../Cap/CapabilityAllocated.h"
#include "../Utils/Single_T.h"

class CapDispatchManager :public Single_T<CapDispatchManager> {
private:
    CapDispatchManager() = default;
    CapDispatchManager(const CapDispatchManager&) = delete;
    CapDispatchManager & operator=(const CapDispatchManager &) = delete;
    ~CapDispatchManager() = default;
    friend class SafeDeletor_T<CapDispatchManager>;
    friend class Single_T<CapDispatchManager>;
public:
    static const int DEST_PORT = 9999;
    void run(CapabilityAllocated* capAllocated);
};


#endif //IROS_CAPDISPATCHMANAGER_H
