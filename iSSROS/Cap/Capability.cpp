//
// Created by zhengyanzhu on 2022/11/4.
//

#include "Capability.h"
#include <iostream>

using namespace std;

Capability::Capability(Capability &capability) {
    this->id = capability.id;
    this->name = capability.name;
//    this->fov = capability.fov;
    this->status = capability.status;
    this->level = capability.level;
    this->parameter = capability.parameter;
    this->position = capability.position;
//    this->resolution = capability.resolution;
}

int Capability::getId() const {
    return id;
}

const string &Capability::getName() const {
    return name;
}



bool Capability::isStatus() const {
    return status;
}

const Parameter &Capability::getParameter() const {
    return parameter;
}

void Capability::setId(int id) {
    Capability::id = id;
}

void Capability::setName(const string &name) {
    Capability::name = name;
}

void Capability::setLevel(vector<float >& level) {
    Capability::level = level;
}

void Capability::setStatus(bool status) {
    Capability::status = status;
}

void Capability::setParameter(const Parameter &parameter) {
    Capability::parameter = parameter;
}

short Capability::getType() const {
    return type;
}

void Capability::setType(short type) {
    Capability::type = type;
}

void Capability::setPosition(Position &position) {
    Capability::position = position;
}

const Position& Capability::getPosition() const {
    return position;
}

void Capability::setVehicleName(const string &vehicleName) {
    Capability::vehicleName = vehicleName;
}

const string &Capability::getVehicleName() const {
    return vehicleName;
}

Capability::Capability() {

}

Capability::~Capability() {

}

Capability::Capability(const CapabilityBuilder &temp) {
    this->id = temp.defaultId;
//    cout<<"builder"<< this->idset <<endl;
    this->name = temp.defaultName;
    this->status = temp.defaultStatus;
    this->level = temp.defaultLevel;
    this->parameter = temp.defaultParameter;
    this->type = temp.defaultType;
    this->position = temp.defaultPosition;
    this->vehicleName = temp.defaultVehicle;
    this->power = temp.defaultPower;
}

void Capability::show() const{
    cout<<"id: "<<id<<endl;
    cout<<"resourceName: "<<name<<endl;
    cout<<"status: "<<status<<endl;
    cout<<"level: ";
    for (int i = 0; i < level.size(); ++i) {
        cout<<level[i]<<" ";
    }
    cout<<endl;
    cout<<"type: "<<type<<endl;
    cout<<"vehicleName: "<<vehicleName<<endl;
    cout << "power: " << power << endl;
    map<string,string> m = parameter.getArgs();
    cout<<"parameters: "<<endl;
    for (map<string, string>::iterator iter = m.begin(); iter != m.end(); ++iter) {
        cout <<"   "<< iter->first << ": " << iter->second << endl;
    }
}

const vector<float> &Capability::getLevel() const {
    return level;
}

float Capability::getPower() const {
    return power;
}

void Capability::setPower(float power) {
    Capability::power = power;
}


CapabilityBuilder::CapabilityBuilder() {
    this->defaultId = 0;
    this->defaultName = "";
    this->defaultStatus = false;
//    this->defaultLevel = 0;
    this->defaultType = 0;
    this->defaultVehicle = "";
    this->defaultPower = 0.0;
//    this->defaultPosition = new Position();
}

CapabilityBuilder *CapabilityBuilder::id(int id) {
    this->defaultId = id;
    return this;
}

CapabilityBuilder *CapabilityBuilder::name(string& name) {
    this->defaultName = name;
    return this;
}

CapabilityBuilder *CapabilityBuilder::level(vector<float >& level) {
    this->defaultLevel = level;
    return this ;
}

CapabilityBuilder *CapabilityBuilder::status(bool status) {
    this->defaultStatus = status;
    return this;
}

CapabilityBuilder *CapabilityBuilder::parameter(Parameter &parameter) {
    this->defaultParameter = parameter;
    return this;
}

CapabilityBuilder::~CapabilityBuilder() {
    delete res;
}

Capability *CapabilityBuilder::build() {
    this->res = new Capability(*this);
    return res;
}

//CapabilityBuilder *CapabilityBuilder::position(Position &position) {
//    this->defaultPosition = position;
//    return this;
//}

CapabilityBuilder *CapabilityBuilder::vehicle(string &vehicle) {
    this->defaultVehicle = vehicle;
    return this;
}
CapabilityBuilder *CapabilityBuilder::power(float power) {
    this->defaultPower = power;
    return this;
}


