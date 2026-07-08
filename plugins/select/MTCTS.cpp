#include "MTCTS.h"
#include "Input.h"

MCTSTree::MCTSTree() {

}

TNode* MCTSTree::BuildTree(){
    TNode *root = new TNode;
    SensorGroup = Input::Getinput();
    for(int i = 0; i < SensorGroup.size(); i++) {
        TNode *tmp = new TNode(SensorGroup[i], 1, 1);
        root->CNode.push_back(tmp);
        BuildDfs(SensorGroup, tmp, i);
    }
    this->root = root;
    return root;
}

void MCTSTree::BuildDfs(std::vector<Sensor*> &SensorGroup, TNode *node, int idx) {
    for(int i = idx + 1; i < SensorGroup.size(); i++) {
        TNode *tmp = new TNode(SensorGroup[i], 1, 1);
        node->CNode.push_back(tmp);
        BuildDfs(SensorGroup, tmp, i);
    }
}

void MCTSTree::GetReq() {
    std::vector<std::pair<int,std::vector<double>>> req;
    TaskReq::SetReq(req);
    for(auto tmp : req) {
        req_[tmp.first] = tmp.second;
        std::sort(req_[tmp.first].begin(),req_[tmp.first].end());
    }
}

void MCTSTree::MCTSTraverse() {
    req_ = {};
    GetReq();//获取目标
    MaxEnergy = INT32_MAX;
    SelectGroup = {};
    for(TNode *tmp : root->CNode) {
        dfs(req_,tmp,0,{});
    }
}

void MCTSTree::MCTSSearch() {
    req_ = {};
    GetReq();//获取目标
    MaxEnergy = INT32_MAX;
    SelectGroup = {};
    for(TNode *tmp : root->CNode) {
        MCTSdfs(req_,tmp,0,{});
    }
}

void MCTSTree::dfs(std::map<int,std::vector<double>> req, TNode* node, int energy, std::vector<Sensor*> vec) {
    if(req.empty() &&energy < MaxEnergy) {
        SelectGroup = vec;
        MaxEnergy = energy;
    }
    if(req.count(node->sen->capId)) {
        int Id = node->sen->capId;
        int i ;
        for(i = 0; i < req[Id].size() - 1; i++) {
            if(req[Id][i + 1] > node->sen->capacity) break;
        }
        if(node->sen->capacity > req[Id][i]) {
            req[Id].erase(req[Id].begin()+i);
            if(req[Id].empty()) {
                req.erase(Id);
            }
            energy += node->sen->energy;
            vec.push_back(node->sen);
        }
    }
    for(TNode *tmp : node->CNode) {
        dfs(req,tmp,energy,vec);
    }
}

void MCTSTree::MCTSdfs(std::map<int,std::vector<double>> req, TNode* node, int energy, std::vector<Sensor*> vec) {
    if(req.empty() &&energy < MaxEnergy) {
        SelectGroup = vec;
        MaxEnergy = energy;
        return;
    }
    if(req.empty()) return;
    if(req.count(node->sen->capId)) {
        int Id = node->sen->capId;
        int i ;
        for(i = 0; i < req[Id].size() - 1; i++) {
            if(req[Id][i + 1] > node->sen->capacity) break;
        }
        if(node->sen->capacity > req[Id][i]) {
            req[Id].erase(req[Id].begin()+i);
            if(req[Id].empty()) {
                req.erase(Id);
            }
            energy += node->sen->energy;
            vec.push_back(node->sen);
        }
    }
    else return;
    for(TNode *tmp : node->CNode) {
        MCTSdfs(req,tmp,energy,vec);
    }
}
void MCTSTree::printGroup() {
    std::cout<<"sumEnergy = "<< MaxEnergy<<std::endl;
    std::cout<<"SensorGroup:"<<std::endl;
    for(Sensor *tmp : SelectGroup) {
        std::cout<<tmp->name_<<std::endl;
    }
}