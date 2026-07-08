//
// Created by zhengyanzhu on 2022/11/7.
//

#include "CapabilityNeed.h"
#include <iostream>

using namespace std;

CapabilityNeed::CapabilityNeed() {
    length = 0;
}

CapabilityNeed::~CapabilityNeed() {

}

//CapabilityNeed::CapabilityNeed(const set<pair<int,string>> &idset){
//    this->idset = idset;
//    length = this->idset.size();
//}
//
//const set<pair<int,string>> &CapabilityNeed::getIdSet() const {
//    return idset;
//}
//
//void CapabilityNeed::setId(const set<pair<int,string>> &idset) {
//    unique_lock<shared_timed_mutex> ulk(mutex_);
//    CapabilityNeed::idset = idset;
//    this->length = this->idset.size();
//    ulk.unlock();
//}

int CapabilityNeed::getLength(){
    return this->length;
}

void CapabilityNeed::add(int id,int time,int demand) {
    unique_lock<shared_timed_mutex> ulk(mutex_);
    this->capneedid.push_back(id);
    this->lasttime.push_back(time);
    this->leveldemand.push_back(demand);
    this->length++;
//    pair<set<pair<int,string>>::iterator,bool> tag = idset.insert(key);
//    if(tag.second == true){
//        length++;
//    }else{
//        cout<<"增加cap need失败"<<endl;
//    }
    ulk.unlock();
}


void CapabilityNeed::show() {
    shared_lock<shared_timed_mutex> slk(mutex_);
    if(isEmpty()){
        cout <<"需求表为空: "<<length<< endl;
        return;
    }
    cout <<"cap need length: "<<length<< endl;
    for (int i = 0; i < length; ++i) {
        pair<int,pair<int,float>> capn = this->getcapneed(i);
        cout<<capn.first<<' '<<capn.second.first<<' '<<capn.second.second<<endl;
    }
//    for (set<pair<int,string>>::iterator iter = idset.begin(); iter != idset.end(); ++iter) {
//        cout << iter->first<<" "<<iter->second<<" "<<endl;;
//    }
    slk.unlock();
}

//void CapabilityNeed::remove(pair<int,string> key) {
//    unique_lock<shared_timed_mutex> ulk(mutex_);
//    if(idset.erase(key) == 0){
//        cout<<"删除cap need失败，不存在元素"<<endl;
//    }else{
//        length--;
//    }
//    ulk.unlock();
//}

//pair<int,string> CapabilityNeed::get(pair<int,string> key) {
//    shared_lock<shared_timed_mutex> slk(mutex_);
//    set<pair<int,string>>::iterator res = idset.find(key);
//    if(idset.find(key) == idset.end()){
//        cout<<"查找cap need失败，不存在元素"<<endl;
//        return pair<int,string>{};
//    }else{
//        return *res;
//    }
//    slk.unlock();
//}

bool CapabilityNeed::isEmpty() {
    return length==0;
}

pair<int,pair<int,float>> CapabilityNeed::getcapneed(int item){
    pair<int, pair<int, float>> temp{capneedid[item], {lasttime[item], leveldemand[item]}};
    return temp;
};
