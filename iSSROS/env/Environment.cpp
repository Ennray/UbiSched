//
// Created by zhengyanzhu on 2022/11/9.
//

#include "Environment.h"

EnvironmentBuilder::EnvironmentBuilder() {
    this->defaultTime =  string("");
    this->defaultLight = 0.0;
}

EnvironmentBuilder *EnvironmentBuilder::weather(Weather& val) {
    this->defaultWeather = val;
    return this;
}

EnvironmentBuilder *EnvironmentBuilder::time(string val) {
    this->defaultTime = val;
    return this;
}

Environment *EnvironmentBuilder::build() {
    unique_lock<shared_timed_mutex> ulk(mutex_);
    res = new Environment(*this);
    ulk.unlock();
    return res;
}

EnvironmentBuilder::~EnvironmentBuilder() {

}

EnvironmentBuilder *EnvironmentBuilder::light(float val) {
    this->defaultLight = val;
    return this;
}

Environment::Environment() {}

Environment::~Environment() {

}

const string Environment::getTime() const {
    return time;
}

float Environment::getLight() const {
    return light;
}

const Weather &Environment::getWeather() const {
    return weather;
}

void Environment::setTime(const string time) {
    Environment::time = time;
}

void Environment::setLight(float light) {
    Environment::light = light;
}

void Environment::setWeather(const Weather &weather) {
    Environment::weather = weather;
}

Environment::Environment(EnvironmentBuilder &tmp) {
    this->time = tmp.defaultTime;
    this->light = tmp.defaultLight;
    this->weather = tmp.defaultWeather;
}

void Environment::show() {
    cout<<"current environment is:"<<endl;
    cout<<"time: "<<time<<endl;
    cout<<"light: "<<light<<endl;
    this->weather.show();
}
