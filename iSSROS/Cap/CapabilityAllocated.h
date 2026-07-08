//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_CAPABILITYALLOCATED_H
#define IROS_CAPABILITYALLOCATED_H
#include <map>
#include <mutex>
#include <shared_mutex>

using namespace std;

//能力分配表map，需求id和分配id
class CapabilityAllocated {
private:
    map<int ,int> id2id;
    volatile int length;
    shared_timed_mutex mutex_;
public:
    int getLength() const;

    CapabilityAllocated();

    const map<int,int> &getId2Id() const;

    CapabilityAllocated(const map<int,int> &id2id);

    virtual ~CapabilityAllocated();

    void setId(const map<int,int> &id2id);
    void add(int key,int value);//空请赋值-1
    void show();
    void remove(int key);
    int get(int key);
    bool isEmpty();
    bool isSatisfied();
};


#endif //IROS_CAPABILITYALLOCATED_H
