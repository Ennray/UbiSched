//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_CAPABILITYNEED_H
#define IROS_CAPABILITYNEED_H
#include <map>
#include <vector>
#include <string>
#include <mutex>
#include <shared_mutex>

using namespace std;

//能力需求表
class CapabilityNeed {
private:
//    set<pair<int,string>> idset;
    // map<int,string> idName;
    // vector<pair<int,vector<float>>> idValue;
    // volatile int length;
    vector<int> capneedid;
    vector<int> lasttime;
    vector<float> leveldemand;

public:
    void add(int id,int time,int demand);
    pair<int,pair<int,float>> getcapneed(int item);

private:
    int length = 0;
    shared_timed_mutex mutex_;
public:


    int getLength();

    CapabilityNeed();
//
//    const set<pair<int,string>> &getIdSet() const;
//
//    CapabilityNeed(const set<pair<int,string>> &idset);

    virtual ~CapabilityNeed();

//    void setId(const set<pair<int,string>> &idset);
    void show();
//    void remove(pair<int,string> key);
//    pair<int,string> get(pair<int,string> key);
    bool isEmpty();
};


#endif //IROS_CAPABILITYNEED_H
