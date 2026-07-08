//
// Created by zhengyanzhu on 2022/11/11.
//

#ifndef IROS_ENVIRONMENT_H
#define IROS_ENVIRONMENT_H
#include "Weather.h"
#include <iostream>
#include <mutex>
#include <shared_mutex>

using namespace std;

class Environment;
class EnvironmentBuilder{
public:
    EnvironmentBuilder();
    EnvironmentBuilder* weather(Weather& val);
    EnvironmentBuilder* time(string val);
    EnvironmentBuilder* light(float val);
    Environment* build();
    ~EnvironmentBuilder();

public:
    shared_timed_mutex mutex_;
    string defaultTime;
    float defaultLight;
    Weather defaultWeather;
    Environment* res;
};

class Environment {
private:
    string time;
    float light;
    Weather weather;
public:
    Environment();
    Environment(EnvironmentBuilder & tmp);

    virtual ~Environment();

    const string getTime() const;

    void setTime(const string time);

    void setLight(float light);

    void setWeather(const Weather &weather);

    float getLight() const;

    const Weather &getWeather() const;
    void show();
};


#endif //IROS_ENVIRONMENT_H
