//
// Created by zhengyanzhu on 2022/11/27.
//

#ifndef IROS_SELECTAPI_H
#define IROS_SELECTAPI_H
#include "../Cap/CapabilityCanUse.h"
#include "../Cap/CapabilityNeed.h"
#include <vector>

// 功能接口类定义
class SelectAPI {
public:
    virtual bool select(const vector<vector<float>>& obs,
    const vector<float>& rnn_states,
    const vector<vector<vector<float>>>& available_actions,
    vector<float>& actions0,
    int UAVid) = 0;
};
#endif //IROS_SELECTAPI_H
