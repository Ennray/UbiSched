#pragma once
#include <string>
#include <vector>
#include "Sensor.h"


class Uav {
public:
    Uav(std::string name, double POS_X, double POX_Y, double POX_Z, double energy);
private:
    std::string name;
    double POS_X;
    double POX_Y;
    double POX_Z;
    double energy;
    std::vector<Sensor> sensors;
};