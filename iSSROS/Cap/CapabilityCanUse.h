//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_CAPABILITYCANUSE_H
#define IROS_CAPABILITYCANUSE_H
#include <map>
#include <mutex>
#include <shared_mutex>
#include "../env/Position.h"
#include <vector>

using namespace std;

//可用能力map，id和level
class CapabilityCanUse {
private:
    int id;
    vector<float > level;
//    volatile int length;
    Position position;
    float power;
    shared_timed_mutex mutex_;
public:
    CapabilityCanUse();
    CapabilityCanUse(int id, const vector<float> &level, const Position &position);
    CapabilityCanUse(int id, const vector<float> &level, const Position &position, float power);
    virtual ~CapabilityCanUse();
    void setPosition(const Position &position);
    const Position &getPosition() const;
//    void show();
//    bool isEmpty();
    int getId() const;
    const vector<float> &getLevel() const;
    void setId(int id);
    void setLevel(const vector<float> &level);
    void setPower(float power);
    float getPower() const;
    CapabilityCanUse(const CapabilityCanUse& temp);
};


#endif //IROS_CAPABILITYCANUSE_H