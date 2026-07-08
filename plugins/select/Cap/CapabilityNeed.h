//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_CAPABILITYNEED_H
#define IROS_CAPABILITYNEED_H
#include <set>
#include <string>
#include <mutex>
#include <shared_mutex>

using namespace std;

//能力需求表，id,name的pair
class CapabilityNeed {
private:
    set<pair<int,string>> idset;
    volatile int length;
    shared_timed_mutex mutex_;
public:
    int getLength() const;

    CapabilityNeed();

    const set<pair<int,string>> &getIdSet() const;

    CapabilityNeed(const set<pair<int,string>> &idset);

    virtual ~CapabilityNeed();

    void setId(const set<pair<int,string>> &idset);
    void add(pair<int,string> key);
    void show();
    void remove(pair<int,string> key);
    pair<int,string> get(pair<int,string> key);
    bool isEmpty();
};


#endif //IROS_CAPABILITYNEED_H
