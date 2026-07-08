#pragma once
#include "TNode.h"
#include "TaskReq.h"
#include <map>
#include <iostream>
#include <algorithm>
#include <vector>
#include "Cap/CapabilityCanUse.h"
#include "Cap/CapabilityNeed.h"
class MCTSTree {
public:
    MCTSTree();
    TNode* BuildTree();
    void BuildDfs( std::vector<Sensor*> &SensorGroup, TNode *node, int idx );
    void GetReq();//获取任务目标
    void MCTSSearch(); //树搜索
    void dfs(std::map<int,std::vector<double>> req, TNode* node, int energy, std::vector<Sensor*> vec);
    void MCTSdfs(std::map<int,std::vector<double>> req, TNode* node, int energy, std::vector<Sensor*> vec);
    void MCTSTraverse();
    void Treversed();//反向迭代
    void SaveRes();//保存结果
    void printGroup();//打印输出
    static  std::map<int, int> Select(vector<CapabilityCanUse> resourceCapCanUseTB,CapabilityNeed* capNeedTB) {return std::map<int, int>{};}
private:
    std::map<int,std::vector<double>> req_;
    std::vector<Sensor*> SensorGroup;
    std::vector<Sensor*> SelectGroup;
    int MaxEnergy = INT32_MAX;
    TNode *root; //根节点指针
    TNode *fp; //当前节点指针
    std::map<int, int> select;//选择输出结果数据结构
};

