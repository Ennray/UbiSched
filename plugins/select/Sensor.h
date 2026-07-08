#pragma once



#include <string>
class Sensor {
public:
    Sensor(std::string name,int capId, double cap, double energy, bool work, int Uavid):name_(name), capId(capId),capacity(cap), energy(energy), working(work), Uavid(Uavid){};

    std::string name_;
    int capId;
    double capacity;
    double energy;
    bool working;
    int Uavid;
};


