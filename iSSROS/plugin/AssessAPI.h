//
// Created by zhengyanzhu on 2022/11/10.
//

#ifndef IROS_ASSESSAPI_H
#define IROS_ASSESSAPI_H


#include "../Cap/Capability.h"
#include "../env/Environment.h"
#include "../Cap/CapabilityAllocated.h"
#include "../Cap/CapabilityCanUse.h"
#include "../Cap/CapabilityNeed.h"
#include <vector>

// 功能接口类定义
class AssessAPI {
public:
    //评估插件
    virtual bool assess(vector<Capability*>& capabilities,Environment* curEnv) = 0;
    //匹配插件
//    virtual bool select(CapabilityCanUse * capCanUseTB,CapabilityNeed* capNeedTB) = 0;
////    virtual CapabilityAllocated* select(CapabilityCanUse * capCanUseTB,CapabilityNeed* capNeedTB) = 0;
//    virtual void test() = 0;
};



#endif //IROS_ASSESSAPI_H
