//
// Created by zhengyanzhu on 2022/11/10.
//

#ifndef IROS_DEMO_H
#define IROS_DEMO_H

#include "Cap/Capability.h"
#include "env/Environment.h"
#include <vector>

// 功能接口类定义
class AssessAPI {
public:
    virtual bool assess(vector<Capability*> &capabilities,Environment* curEnv) = 0;
};



#endif //IROS_DEMO_H
