#pragma once

#include <string>
#include <vector>
#include "Uav.h"
#include "Sensor.h"
class TNode {
public:
    TNode();
    Sensor *sen;
    TNode(Sensor *sen,int n, int rev);
    std::vector<TNode*> CNode; //子节点
private:

    int  node_n;// 上置信区间N
    int reversed;// 反向迭代
};