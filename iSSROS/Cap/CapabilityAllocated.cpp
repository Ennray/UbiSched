//
// Created by zhengyanzhu on 2022/11/7.
//

#include <iostream>
#include "CapabilityAllocated.h"

int CapabilityAllocated::getLength() const {
    return length;
}

CapabilityAllocated::CapabilityAllocated() {
    this->length = 0;
}

const map<int, int> &CapabilityAllocated::getId2Id() const {
    return id2id;
}

CapabilityAllocated::CapabilityAllocated(const map<int,int> &id2id) {
    unique_lock<shared_timed_mutex> ulk(mutex_);
    this->id2id = id2id;
    this->length = this->id2id.size();
    ulk.unlock();
}

CapabilityAllocated::~CapabilityAllocated() {

}

void CapabilityAllocated::setId(const map<int, int> &id2id) {
    unique_lock<shared_timed_mutex> ulk(mutex_);
    this->id2id = id2id;
    this->length = this->id2id.size();
    ulk.unlock();
}


void CapabilityAllocated::add(int key, int value) {
    unique_lock<shared_timed_mutex> ulk(mutex_);
    if(id2id.count(key) == 0){
        id2id[key] = value;
        length++;
    }else{
        cout<<"增加cap canUse失败"<<endl;
    }
    ulk.unlock();
}

void CapabilityAllocated::show() {
    shared_lock<shared_timed_mutex> slk(mutex_);
    cout <<"cap allocated length: "<<length<< endl;
    for (map<int,int>::iterator iter = id2id.begin(); iter != id2id.end(); ++iter) {
        cout << iter->first<<" "<<iter->second<<" "<<endl;
    }
    slk.unlock();
}

void CapabilityAllocated::remove(int key) {
    unique_lock<shared_timed_mutex> ulk(mutex_);
    if(id2id.count(key) == 0){
        cout<<"删除cap allocated失败，key不存在"<<endl;
    }else{
        id2id.erase(key);
        length--;
    }
    ulk.unlock();
}

int CapabilityAllocated::get(int key) {
    shared_lock<shared_timed_mutex> slk(mutex_);
    if(id2id.count(key) == 0){
        cout<<"获取cap canUse失败，key不存在"<<endl;
        return 0;
    }else{
        return id2id[key];
    }
}

bool CapabilityAllocated::isEmpty() {
    return length == 0;
}

bool CapabilityAllocated::isSatisfied() {
    shared_lock<shared_timed_mutex> slk(mutex_);
    for (map<int,int>::iterator iter = id2id.begin(); iter != id2id.end(); ++iter) {
        if(iter->second == -1){
            return false;
        }
    }
    slk.unlock();
    return true;
}
