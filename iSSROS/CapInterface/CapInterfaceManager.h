//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_CAPINTERFACEMANAGER_H
#define IROS_CAPINTERFACEMANAGER_H
#include "../Cap/Capability.h"
#include "../Utils/Single_T.h"
#include "../Resource/Resource.h"
#include <vector>

class CapInterfaceManager :public Single_T<CapInterfaceManager>{
private:
    CapInterfaceManager() = default;
    CapInterfaceManager(const CapInterfaceManager&) = delete;
    CapInterfaceManager & operator=(const CapInterfaceManager &) = delete;
    ~CapInterfaceManager() = default;
    friend class SafeDeletor_T<CapInterfaceManager>;
    friend class Single_T<CapInterfaceManager>;

public:
    vector<Capability*> getCapabilityFromTxt(const char* filePath) const;
};


#endif //IROS_CAPINTERFACEMANAGER_H
