//
// Created by zhengyanzhu on 2022/11/7.
//

#include <iostream>
#include "CapabilityCanUse.h"

//int CapabilityCanUse::getLength() const {
//    return length;
//}



//const map<int, float> &CapabilityCanUse::getIdLevel() const {
//    return idLevel;
//}
//
//CapabilityCanUse::CapabilityCanUse(const map<int, float> &idLevel) {
//    this->idLevel = idLevel;
//    this->length = this->idLevel.size();
//}

CapabilityCanUse::~CapabilityCanUse() {

}

//int CapabilityCanUse::getId() const {
//    return id;
//}
//
//void CapabilityCanUse::setId(int id) {
//    CapabilityCanUse::id = id;
//}
//
//void CapabilityCanUse::setResourceName(const string &resourceName) {
//    CapabilityCanUse::resourceName = resourceName;
//}
//
//void CapabilityCanUse::setLevel(float level) {
//    CapabilityCanUse::level = level;
//}
//
//void CapabilityCanUse::setPosition(const Position &position) {
//    CapabilityCanUse::position = position;
//}
//
//const string &CapabilityCanUse::getResourceName() const {
//    return resourceName;
//}
//
//float CapabilityCanUse::getLevel() const {
//    return level;
//}
//
//const Position &CapabilityCanUse::getPosition() const {
//    return position;
//}
//
//CapabilityCanUse::CapabilityCanUse(int id, string &resourceName, float level, Position &position) {
//    this->id = id;
//    this->resourceName = resourceName;
//    this->level = level;
//    this->position = position;
//}



//void CapabilityCanUse::add(int key,vector<float > &value) {
//    unique_lock<shared_timed_mutex> ulk(mutex_);
//    if(idLevel.count(key) == 0){
//        idLevel[key] = value;
//        length++;
//    }else{
//        cout<<"增加cap canUse失败"<<endl;
//    }
//    ulk.unlock();
//}

//void CapabilityCanUse::show() {
//    shared_lock<shared_timed_mutex> slk(mutex_);
//    cout <<"cap canUse length: "<<length<< endl;
//    for (map<int,vector<float >>::iterator iter = idLevel.begin(); iter != idLevel.end(); ++iter) {
//        vector<float> cur = iter->second;
//        cout << iter->first<<": ";
//        for (int i = 0; i < cur.size(); ++i) {
//            cout<<cur[i]<<" ";
//        }
//        cout <<endl;
//    }
//    slk.unlock();
//}

//void CapabilityCanUse::remove(int key) {
//    unique_lock<shared_timed_mutex> ulk(mutex_);
//    if(idLevel.count(key) == 0){
//        cout<<"删除cap canUse失败，key不存在"<<endl;
//    }else{
//        idLevel.erase(key);
//        length--;
//    }
//    ulk.unlock();
//}

//vector<float >& CapabilityCanUse::get(int key) {
//    shared_lock<shared_timed_mutex> slk(mutex_);
//    if(idLevel.count(key) == 0){
//        cout<<"获取cap canUse失败，key不存在"<<endl;
//        vector<float > a;
//        return a;
//    }else{
//        return idLevel[key];
//    }
//    slk.unlock();
//}


int CapabilityCanUse::getId() const {
    return id;
}

const vector<float> &CapabilityCanUse::getLevel() const {
    return level;
}

void CapabilityCanUse::setId(int id) {
    CapabilityCanUse::id = id;
}

void CapabilityCanUse::setLevel(const vector<float> &level) {
    CapabilityCanUse::level = level;
}

void CapabilityCanUse::setPosition(const Position &position) {
    CapabilityCanUse::position = position;
}

const Position &CapabilityCanUse::getPosition() const {
    return this->position;
}

CapabilityCanUse::CapabilityCanUse() {}

CapabilityCanUse::CapabilityCanUse(const CapabilityCanUse &temp) {
    this->id = temp.id;
    this->level = temp.level;
    this->position = temp.position;
}

CapabilityCanUse::CapabilityCanUse(int id, const vector<float> &level, const Position &position) : id(id), level(level),
                                                                                                   position(position) {}

CapabilityCanUse::CapabilityCanUse(int id, const vector<float> &level, const Position &position,
                                   float power) : id(id), level(level), position(position),
                                                  power(power) {}

float CapabilityCanUse::getPower() const {
    return power;
}

void CapabilityCanUse::setPower(float power) {
    CapabilityCanUse::power = power;
}


