//
// Created by zhengyanzhu on 2022/11/11.
//

#ifndef IROS_CAPABILITY_H
#define IROS_CAPABILITY_H

#include <string>
#include "Parameter.h"
#include "../env/Position.h"
#include <vector>

using namespace std;

class Capability;

class CapabilityBuilder{
public:
    CapabilityBuilder();
    CapabilityBuilder* id(int id);
    CapabilityBuilder* name(string& name);
    CapabilityBuilder* level(vector<float > &level);
    CapabilityBuilder* status(bool status);
    CapabilityBuilder* parameter(Parameter& parameter);
//    CapabilityBuilder* position(Position& position);
    CapabilityBuilder* vehicle(string &vehicle);
    Capability * build();
    ~CapabilityBuilder();

public:
    int defaultId;
    string defaultName;
    vector<float > defaultLevel;
    bool defaultStatus;
    short defaultType;//0:原子 1:复合
    Parameter defaultParameter;
    Position defaultPosition;
    string defaultVehicle;
    Capability* res;

};

class Capability {
public:
    Capability();
    Capability(CapabilityBuilder const &temp);
    Capability(Capability &capability);
    void show() const;
    virtual ~Capability();

    int getId() const;

    const string &getName() const;

    const vector<float> &getLevel() const;

    bool isStatus() const;

    const Parameter &getParameter() const;

    void setId(int id);

    void setName(const string &name);

    void setLevel(vector<float >& level);

    void setStatus(bool status);

    void setParameter(const Parameter &parameter);

    short getType() const;

    void setPosition(Position& position);

    const Position &getPosition() const;
    void setType(short type);

    void setVehicleName(const string &vehicleName);

    const string &getVehicleName() const;

private:
    int id;
    string name;
    vector<float > level;
    bool status;
    short type;//0:原子 1:复合
    Parameter parameter;
    Position position;

private:
//能力的位置
    string vehicleName;
};

#endif //IROS_CAPABILITY_H

