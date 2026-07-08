#pragma once
#include <vector>
#include <string>
class TaskReq {
public:
    TaskReq();
    static void  SetReq(std::vector<std::pair<int,std::vector<double>>> &req_);
    //static::std::vector<std::pair<std::string,double>> req_;
    double POS_X;
    double POS_Y;
    double POS_Z;
};



